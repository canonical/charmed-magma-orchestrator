# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, PropertyMock, call, patch

from ops import testing
from ops.model import ActiveStatus, BlockedStatus
from ops.pebble import ExecError
from pgconnstr import ConnectionString  # type: ignore[import]

from charm import MagmaNmsMagmalteCharm, ServiceNotRunningError


class MockExec:
    def __init__(self, *args, **kwargs):
        if "raise_exec_error" in kwargs:
            self.raise_exec_error = True
        else:
            self.raise_exec_error = False

    def exec(self, *args, **kwargs):
        pass

    def wait_output(self, *args, **kwargs):
        if self.raise_exec_error:
            raise ExecError(command=["blob"], exit_code=1234, stdout="", stderr="")


class TestCharm(unittest.TestCase):
    TEST_DB_NAME = MagmaNmsMagmalteCharm.DB_NAME
    TEST_DB_PORT = "1234"
    TEST_DB_CONNECTION_STRING = ConnectionString(
        "dbname=test_db_name "
        "fallback_application_name=whatever "
        "host=123.456.789.012 "
        "password=aaaBBBcccDDDeee "
        "port=1234 "
        "user=test_db_user"
    )
    TEST_DOMAIN_NAME = "test.domain.com"
    GRAFANA_URLS = ["auth-requirer:3000"]

    @patch(
        "charm.KubernetesServicePatch", lambda charm, ports, service_name, additional_labels: None
    )
    @patch("pgsql.opslib.pgsql.client.PostgreSQLClient._mirror_appdata", new=Mock())
    def setUp(self):
        self.namespace = "whatever"
        self.harness = testing.Harness(MagmaNmsMagmalteCharm)
        self.harness.set_model_name(name=self.namespace)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.grafana_auth_rel_id = self.harness.add_relation("grafana-auth", "auth-requirer")
        self.harness.set_leader(True)
        self.peer_relation_id = self.harness.add_relation("replicas", self.harness.charm.app.name)
        self.harness.add_relation_unit(self.peer_relation_id, self.harness.charm.unit.name)

    @staticmethod
    def _fake_db_event(
        postgres_db_name: str,
        postgres_username: str,
        postgres_password: str,
        postgres_host: str,
        postgres_port: str,
    ):
        db_event = Mock()
        db_event.master = Mock()
        db_event.master.dbname = postgres_db_name
        db_event.master.user = postgres_username
        db_event.master.password = postgres_password
        db_event.master.host = postgres_host
        db_event.master.port = postgres_port
        return db_event

    def test_given_db_relation_not_created_when_pebble_ready_then_unit_is_in_blocked_state(  # noqa: E501
        self,
    ):
        self.harness.add_relation(
            relation_name="cert-admin-operator", remote_app="magma-orc8r-certifier"
        )
        self.harness.container_pebble_ready(container_name="magma-nms-magmalte")

        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for db relation to be created"),
        )

    def test_given_cert_admin_operator_relation_not_created_when_pebble_ready_then_unit_is_in_blocked_state(  # noqa: E501
        self,
    ):
        self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")

        self.harness.container_pebble_ready(container_name="magma-nms-magmalte")

        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for cert-admin-operator relation to be created"),
        )

    def test_given_grafana_auth_relation_not_created_when_pebble_ready_then_unit_is_in_blocked_state(  # noqa: E501
        self,
    ):
        self.harness.add_relation(
            relation_name="cert-admin-operator", remote_app="magma-orc8r-certifier"
        )
        self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        self.harness.remove_relation(self.grafana_auth_rel_id)

        self.harness.container_pebble_ready(container_name="magma-nms-magmalte")

        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for grafana-auth relation to be created"),
        )

    @patch("charm.MagmaNmsMagmalteCharm.DB_NAME", new_callable=PropertyMock)
    @patch("ops.model.Unit.is_leader", Mock())
    def test_given_pod_is_leader_when_database_relation_joined_event_then_database_is_set_correctly(  # noqa: E501
        self, mock_db_name
    ):
        mock_db_name.return_value = self.TEST_DB_NAME
        postgres_db_name = self.TEST_DB_NAME
        postgres_host = "bread"
        postgres_password = "water"
        postgres_username = "yeast"
        postgres_port = self.TEST_DB_PORT

        db_event = self._fake_db_event(
            postgres_db_name,
            postgres_username,
            postgres_password,
            postgres_host,
            postgres_port,
        )
        self.harness.charm._on_database_relation_joined(db_event)

        self.assertEqual(db_event.database, self.TEST_DB_NAME)

    @patch("ops.model.Container.exec", new=Mock())
    @patch("ops.model.Container.exists")
    @patch("psycopg2.connect", new=Mock())
    @patch("charm.ConnectionString")
    @patch("charm.MagmaNmsMagmalteCharm._grafana_url", new_callable=PropertyMock)
    def test_given_relations_are_created_and_certs_are_stored_and_grafana_urls_are_available_when_pebble_ready_then_pebble_plan_is_filled_with_magma_nms_magmalte_service_content(  # noqa: E501
        self, grafana_url_mock, patch_connection_string, patch_file_exists
    ):
        grafana_url_mock.return_value = self.GRAFANA_URLS[0]
        patch_file_exists.return_value = True
        db_relation_id = self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        self.harness.add_relation(
            relation_name="cert-admin-operator", remote_app="magma-orc8r-certifier"
        )
        key_values = {"master": str(self.TEST_DB_CONNECTION_STRING)}
        self.harness.update_relation_data(
            relation_id=db_relation_id, key_values=key_values, app_or_unit="postgresql-k8s"
        )
        patch_connection_string.return_value = self.TEST_DB_CONNECTION_STRING

        self.harness.container_pebble_ready(container_name="magma-nms-magmalte")
        expected_plan = {
            "services": {
                "magma-nms-magmalte": {
                    "startup": "enabled",
                    "override": "replace",
                    "command": f"/usr/local/bin/wait-for-it.sh -s -t 30 "
                    f"{self.TEST_DB_CONNECTION_STRING.host}:"
                    f"{self.TEST_DB_CONNECTION_STRING.port} -- "
                    f"yarn run start:prod",
                    "environment": {
                        "API_CERT_FILENAME": "/run/secrets/admin_operator.pem",
                        "API_PRIVATE_KEY_FILENAME": "/run/secrets/admin_operator.key.pem",
                        "API_HOST": f"orc8r-nginx-proxy.{self.namespace}.svc.cluster.local",
                        "PORT": "8081",
                        "HOST": "0.0.0.0",
                        "MYSQL_HOST": self.TEST_DB_CONNECTION_STRING.host,
                        "MYSQL_PORT": self.TEST_DB_CONNECTION_STRING.port,
                        "MYSQL_DB": self.TEST_DB_NAME,
                        "MYSQL_USER": self.TEST_DB_CONNECTION_STRING.user,
                        "MYSQL_PASS": self.TEST_DB_CONNECTION_STRING.password,
                        "MAPBOX_ACCESS_TOKEN": "",
                        "MYSQL_DIALECT": "postgres",
                        "PUPPETEER_SKIP_DOWNLOAD": "true",
                        "USER_GRAFANA_ADDRESS": self.GRAFANA_URLS[0],
                    },
                },
            },
        }

        updated_plan = self.harness.get_container_pebble_plan("magma-nms-magmalte").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    @patch("ops.model.Container.exec", new=Mock())
    @patch("ops.model.Container.exists")
    @patch("psycopg2.connect", new=Mock())
    @patch("charm.ConnectionString")
    @patch("charm.MagmaNmsMagmalteCharm._grafana_url", new_callable=PropertyMock)
    def test_given_relations_are_created_and_certs_are_stored_and_grafana_urls_are_available_when_pebble_ready_then_charm_goes_to_active_state(  # noqa: E501
        self,
        grafana_url_mock,
        patch_connection_string,
        patch_exists,
    ):
        grafana_url_mock.return_value = self.GRAFANA_URLS[0]
        patch_exists.return_value = True
        patch_connection_string.return_value = self.TEST_DB_CONNECTION_STRING
        self.harness.add_relation(
            relation_name="cert-admin-operator", remote_app="magma-orc8r-certifier"
        )
        db_relation_id = self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        key_values = {"master": str(self.TEST_DB_CONNECTION_STRING)}
        self.harness.update_relation_data(
            relation_id=db_relation_id, key_values=key_values, app_or_unit="postgresql-k8s"
        )

        self.harness.container_pebble_ready(container_name="magma-nms-magmalte")

        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())

    @patch("ops.model.Container.exec", new=Mock())
    @patch("ops.model.Container.exists")
    @patch("psycopg2.connect", new=Mock())
    @patch("charm.ConnectionString")
    def test_given_pebble_ready_when_db_relation_broken_then_status_is_blocked(  # noqa: E501
        self, patch_connection_string, patch_exists
    ):
        event = Mock()
        event.urls = self.GRAFANA_URLS
        self.harness.charm._on_grafana_urls_available(event=event)
        patch_exists.return_value = True
        patch_connection_string.return_value = self.TEST_DB_CONNECTION_STRING
        self.harness.add_relation(
            relation_name="cert-admin-operator", remote_app="magma-orc8r-certifier"
        )
        db_relation_id = self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        key_values = {"master": str(self.TEST_DB_CONNECTION_STRING)}
        self.harness.update_relation_data(
            relation_id=db_relation_id, key_values=key_values, app_or_unit="postgresql-k8s"
        )
        self.harness.container_pebble_ready(container_name="magma-nms-magmalte")

        self.harness.remove_relation(db_relation_id)
        self.assertEqual(
            self.harness.charm.unit.status, BlockedStatus("Waiting for db relation to be created")
        )

    @patch("ops.model.Container.get_service", new=Mock())
    @patch("ops.model.Container.exec")
    @patch("charm.MagmaNmsMagmalteCharm._get_db_connection_string", new_callable=PropertyMock)
    def test_given_username_email_and_password_are_provided_and_service_is_running_and_unit_is_leader_when_create_nms_admin_user_juju_action_then_pebble_command_is_executed(  # noqa: E501
        self, _, mock_exec
    ):
        container = self.harness.model.unit.get_container("magma-nms-magmalte")
        self.harness.set_can_connect(container=container, val=True)
        action_event = Mock(
            params={
                "email": "test@test.test",
                "organization": "test-org",
                "password": "password123",
            }
        )
        self.harness.charm._create_nms_admin_user_action(action_event)
        args, _ = mock_exec.call_args
        mock_exec.assert_called_once()
        call_command = [
            "/usr/local/bin/yarn",
            "setAdminPassword",
            "test-org",
            "test@test.test",
            "password123",
        ]
        self.assertIn(call_command, args)

    def test_given_username_email_and_password_are_provided_and_unit_is_not_leader_when_create_nms_admin_user_juju_action_then_action_returns_error(  # noqa: E501
        self,
    ):
        action_event = Mock(
            params={
                "email": "test@test.test",
                "organization": "test-org",
                "password": "password123",
            }
        )
        self.harness.set_leader(False)
        self.harness.charm._create_nms_admin_user_action(action_event)

        self.assertEqual(
            action_event.fail.call_args,
            [("This action needs to be run on the leader",)],
        )

    def test_given_one_of_username_email_and_password_is_missing_when_create_nms_admin_user_juju_action_then_action_fails(  # noqa: E501
        self,
    ):
        action_event_params_org_is_missing = {"email": "test@test.test", "password": "password123"}
        action_event = Mock(params=action_event_params_org_is_missing)
        with self.assertRaises(KeyError):
            self.harness.charm._create_nms_admin_user_action(action_event)

    @patch("ops.model.Container.exec")
    @patch("charm.MagmaNmsMagmalteCharm._get_db_connection_string", new_callable=PropertyMock)
    @patch("ops.charm.ActionEvent")
    def test_given_juju_action_when_workload_service_not_running_then_user_is_not_created_and_raises_exception(  # noqa: E501
        self, action_event, _, mock_exec
    ):
        mock_exec.assert_not_called()
        mock_exec.side_effect = ServiceNotRunningError(
            "Service should be running for the user to be created"
        )
        with self.assertRaises(ServiceNotRunningError):
            self.harness.charm._create_nms_admin_user_action(action_event)

    @patch("ops.model.Container.get_service", new=Mock())
    @patch("ops.model.Container.exec")
    @patch("charm.MagmaNmsMagmalteCharm._get_db_connection_string", new_callable=PropertyMock)
    @patch("ops.charm.ActionEvent")
    def test_given_juju_action_when_user_creation_fails_then_action_raises_an_error(
        self, action_event, _, mock_exec
    ):
        container = self.harness.model.unit.get_container("magma-nms-magmalte")
        self.harness.set_can_connect(container=container, val=True)
        mock_exec.side_effect = ExecError(["drop"], 1, "exec error", "mock exec error")
        with self.assertRaises(ExecError):
            self.harness.charm._create_nms_admin_user_action(action_event)

    def test_given_relations_not_created_when_juju_action_then_get_admin_credentials_fails(
        self,
    ):
        action_event = Mock()
        self.harness.charm._on_get_master_admin_credentials(action_event)
        self.assertEqual(
            action_event.fail.call_args,
            [("Workload service is not yet running",)],
        )

    @patch("ops.model.Container.get_service", new=Mock())
    @patch("ops.charm.ActionEvent")
    def test_given_relations_not_created_and_unit_is_not_leader_when_juju_action_then_get_admin_credentials_fails(  # noqa: E501
        self, action_event
    ):
        self.harness.charm._on_get_master_admin_credentials(action_event)
        self.harness.set_leader(False)
        self.assertEqual(
            action_event.fail.call_args,
            [("Admin credentials have not been created yet",)],
        )

    @patch("ops.model.Container.get_service", new=Mock())
    @patch("ops.charm.ActionEvent")
    def test_given_workload_service_is_running_and_peer_relation_not_created_when_get_admin_credentials_action_then_get_admin_credentials_fail(  # noqa: E501
        self, action_event
    ):
        self.harness.remove_relation(self.peer_relation_id)
        self.harness.charm._on_get_master_admin_credentials(action_event)

        self.assertEqual(
            action_event.fail.call_args,
            [("Peer relation not created yet",)],
        )

    @patch("ops.model.Container.get_service", new=Mock())
    @patch("ops.charm.ActionEvent")
    def test_given_workload_service_is_running_and_unit_is_leader_when_get_admin_credentials_action_then_username_and_password_are_returned(  # noqa: E501
        self, action_event
    ):
        self.harness.update_relation_data(
            relation_id=self.peer_relation_id,
            app_or_unit=self.harness.charm.app.name,
            key_values={"admin_password": "password"},
        )

        self.harness.charm._on_get_master_admin_credentials(action_event)

        self.assertEqual(
            action_event.set_results.call_args,
            [({"admin-username": "admin@juju.com", "admin-password": "password"},)],
        )

    @patch("ops.model.Container.get_service", new=Mock())
    @patch("ops.charm.ActionEvent")
    def test_given_workload_service_is_running_and_unit_is_not_leader_when_get_admin_credentials_action_then_username_and_password_are_returned(  # noqa: E501
        self, action_event
    ):
        self.harness.update_relation_data(
            relation_id=self.peer_relation_id,
            app_or_unit=self.harness.charm.app.name,
            key_values={"admin_password": "password"},
        )

        self.harness.set_leader(False)
        self.harness.charm._on_get_master_admin_credentials(action_event)

        self.assertEqual(
            action_event.set_results.call_args,
            [({"admin-username": "admin@juju.com", "admin-password": "password"},)],
        )

    @patch("ops.model.Container.push")
    def test_given_pebble_ready_when_certificate_available_then_certs_are_pushed_to_container(
        self, patch_push
    ):
        certificate = "whatever certificate"
        private_key = "whatever private key"
        event = Mock()
        event.certificate = certificate
        event.private_key = private_key

        container = self.harness.model.unit.get_container("magma-nms-magmalte")
        self.harness.set_can_connect(container=container, val=True)

        self.harness.charm._on_certificate_available(event=event)

        patch_push.assert_has_calls(
            calls=[
                call(path="/run/secrets/admin_operator.pem", source=certificate),
                call(path="/run/secrets/admin_operator.key.pem", source=private_key),
            ]
        )

    def test_given_grafana_auth_relation_when_urls_available_event_then_grafana_urls_are_stored_in_peer_data(  # noqa: E501
        self,
    ):
        event = Mock()
        event.urls = self.GRAFANA_URLS
        self.harness.charm._on_grafana_urls_available(event=event)
        url = self.harness.get_relation_data(
            self.peer_relation_id, self.harness.charm.app.name
        ).get("grafana_url")
        self.assertEqual("auth-requirer:3000", url)

    def test_given_nms_magmalte_service_not_running_when_magma_nms_magmalte_relation_joined_then_service_active_status_in_the_relation_data_bag_is_false(  # noqa: E501
        self,
    ):
        app_name = self.harness.model.app.name

        relation_id = self.harness.add_relation("magma-nms-magmalte", app_name)
        self.harness.add_relation_unit(relation_id, f"{app_name}/0")

        self.assertEqual(
            self.harness.get_relation_data(relation_id, f"{app_name}/0")["active"],
            "False",
        )

    @patch("ops.model.Container.exec", new=Mock())
    @patch("ops.model.Container.exists")
    @patch("psycopg2.connect", new=Mock())
    @patch("charm.ConnectionString")
    @patch("charm.MagmaNmsMagmalteCharm._grafana_url", new_callable=PropertyMock)
    def test_given_nms_magmalte_service_running_when_magma_nms_magmalte_relation_joined_then_service_active_status_in_the_relation_data_bag_is_true(  # noqa: E501
        self, grafana_url_mock, patch_connection_string, patch_exists
    ):
        app_name = self.harness.model.app.name
        grafana_url_mock.return_value = self.GRAFANA_URLS[0]
        patch_exists.return_value = True
        patch_connection_string.return_value = self.TEST_DB_CONNECTION_STRING
        self.harness.add_relation(
            relation_name="cert-admin-operator", remote_app="magma-orc8r-certifier"
        )
        db_relation_id = self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        key_values = {"master": str(self.TEST_DB_CONNECTION_STRING)}
        self.harness.update_relation_data(
            relation_id=db_relation_id, key_values=key_values, app_or_unit="postgresql-k8s"
        )
        self.harness.container_pebble_ready(container_name="magma-nms-magmalte")

        relation_id = self.harness.add_relation("magma-nms-magmalte", app_name)
        self.harness.add_relation_unit(relation_id, f"{app_name}/0")

        self.assertEqual(
            self.harness.get_relation_data(relation_id, f"{app_name}/0")["active"],
            "True",
        )

    @patch("charm.MagmaNmsMagmalteCharm.NMS_MAGMALTE_K8S_SERVICE_NAME", new_callable=PropertyMock)
    @patch("charm.MagmaNmsMagmalteCharm.NMS_MAGMALTE_K8S_SERVICE_PORT", new_callable=PropertyMock)
    def test_given_no_nms_magmalte_relation_when_magma_nms_magmalte_relation_joined_then_magmalte_k8s_service_details_are_published_in_the_relation_data_bag(  # noqa: E501
        self, patched_service_port, patched_service_name
    ):
        test_magmalte_k8s_service_name = "mud"
        test_magmalte_k8s_service_port = 44
        patched_service_name.return_value = test_magmalte_k8s_service_name
        patched_service_port.return_value = test_magmalte_k8s_service_port
        app_name = self.harness.model.app.name

        relation_id = self.harness.add_relation("magma-nms-magmalte", app_name)
        self.harness.add_relation_unit(relation_id, f"{app_name}/0")

        self.assertEqual(
            self.harness.get_relation_data(relation_id, f"{app_name}/0")["k8s_service_name"],
            test_magmalte_k8s_service_name,
        )
        self.assertEqual(
            self.harness.get_relation_data(relation_id, f"{app_name}/0")["k8s_service_port"],
            str(test_magmalte_k8s_service_port),
        )
