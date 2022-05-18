# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, PropertyMock, patch

from ops import testing
from ops.model import ActiveStatus, BlockedStatus
from ops.pebble import ExecError
from pgconnstr import ConnectionString  # type: ignore[import]

from charm import MagmaNmsMagmalteCharm

testing.SIMULATE_CAN_CONNECT = True


class MockExec:
    def __init__(self, *args, **kwargs):
        if "raise_exec_error" in kwargs:
            self.raise_exec_error = True
        else:
            self.raise_exec_error = False

    def exec(self, *args, **kwargs):
        pass

    def wait_output(self, *args, **kwargs):
        if hasattr(self, "raise_exec_error") and self.raise_exec_error:
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

    @patch(
        "charm.KubernetesServicePatch", lambda charm, ports, service_name, additional_labels: None
    )
    def setUp(self):
        self.harness = testing.Harness(MagmaNmsMagmalteCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

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

    def test_given_charm_when_pebble_ready_event_emitted_and_no_relations_established_then_charm_goes_to_blocked_state(  # noqa: E501
        self,
    ):
        event = Mock()

        self.harness.charm.on.magma_nms_magmalte_pebble_ready.emit(event)

        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for relation(s) to be created: certifier, db"),
        )

    def test_given_charm_when_pebble_ready_event_emitted_and_certifier_relation_is_established_but_db_relation_is_missing_then_charm_goes_to_blocked_state(  # noqa: E501
        self,
    ):
        event = Mock()
        relation_id = self.harness.add_relation("certifier", "orc8r-certifier")
        self.harness.add_relation_unit(relation_id, "orc8r-certifier/0")

        self.harness.charm.on.magma_nms_magmalte_pebble_ready.emit(event)

        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for relation(s) to be created: db"),
        )

    @patch("charm.MagmaNmsMagmalteCharm.DB_NAME", new_callable=PropertyMock)
    @patch("ops.model.Unit.is_leader")
    def test_given_pod_is_leader_when_database_relation_joined_event_then_database_is_set_correctly(  # noqa: E501
        self, _, mock_db_name
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

    @patch("ops.model.Container.exec")
    @patch("charm.MagmaNmsMagmalteCharm._get_db_connection_string", new_callable=PropertyMock)
    @patch("charm.MagmaNmsMagmalteCharm._domain_name", new_callable=PropertyMock)
    @patch("charm.MagmaNmsMagmalteCharm._namespace", new_callable=PropertyMock)
    @patch("charm.MagmaNmsMagmalteCharm._relations_ready", new_callable=PropertyMock)
    def test_given_ready_when_get_plan_then_plan_is_filled_with_magma_nms_magmalte_service_content(
        self, relations_ready, patch_namespace, _, get_db_connection_string, mock_exec
    ):
        namespace = "whatever"
        relations_ready.return_value = True
        patch_namespace.return_value = namespace
        get_db_connection_string.return_value = self.TEST_DB_CONNECTION_STRING

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
                        "API_HOST": f"orc8r-nginx-proxy.{namespace}.svc.cluster.local",
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
                        "USER_GRAFANA_ADDRESS": "orc8r-user-grafana:3000",
                    },
                },
            },
        }

        updated_plan = self.harness.get_container_pebble_plan("magma-nms-magmalte").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    @patch("ops.model.Container.exec")
    @patch("charm.MagmaNmsMagmalteCharm._get_db_connection_string", new_callable=PropertyMock)
    @patch("charm.MagmaNmsMagmalteCharm._domain_name", new_callable=PropertyMock)
    @patch("charm.MagmaNmsMagmalteCharm._configure_pebble")
    @patch("charm.MagmaNmsMagmalteCharm._relations_ready")
    def test_given_charm_when_pebble_ready_event_emitted_and_relations_are_established_configure_pebble_action_is_called(  # noqa: E501
        self, relations_ready, mock_configure_pebble, _, get_db_connection_string, mock_exec
    ):
        relations_ready.return_value = True
        get_db_connection_string.return_value = self.TEST_DB_CONNECTION_STRING
        event = Mock()

        self.harness.charm.on.magma_nms_magmalte_pebble_ready.emit(event)

        mock_configure_pebble.assert_called_once()

    @patch("ops.model.Container.exec")
    @patch("charm.MagmaNmsMagmalteCharm._domain_name", new_callable=PropertyMock)
    @patch("charm.MagmaNmsMagmalteCharm._get_db_connection_string", new_callable=PropertyMock)
    @patch("charm.MagmaNmsMagmalteCharm._relations_ready")
    def test_given_charm_when_pebble_ready_event_emitted_and_relations_are_established_then_charm_goes_to_active_state(  # noqa: E501
        self, relations_ready, get_db_connection_string, _, mock_exec
    ):
        relations_ready.return_value = True
        get_db_connection_string.return_value = self.TEST_DB_CONNECTION_STRING

        self.harness.container_pebble_ready(container_name="magma-nms-magmalte")

        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())

    @patch("ops.model.Container.exec")
    @patch("charm.MagmaNmsMagmalteCharm._get_db_connection_string", new_callable=PropertyMock)
    @patch("ops.charm.ActionEvent")
    def test_given_juju_action_when_create_nms_admin_user_is_called_command_executed_on_container(
        self, action_event, _, mock_exec
    ):
        self.harness.charm._create_nms_admin_user_action(action_event)
        mock_exec.assert_called_once()

    @patch("ops.model.Container.exec")
    @patch("charm.MagmaNmsMagmalteCharm._get_db_connection_string", new_callable=PropertyMock)
    @patch("ops.charm.ActionEvent")
    def test_given_juju_action_when_user_creation_fails_then_action_raises_an_error(
        self, action_event, _, mock_exec
    ):
        mock_exec.return_value = MockExec(raise_exec_error=True)
        with self.assertRaises(ExecError):
            self.harness.charm._create_nms_admin_user_action(action_event)

    @patch("charm.MagmaNmsMagmalteCharm._relations_ready", new_callable=PropertyMock)
    def test_given_juju_action_when_relation_is_not_realized_then_get_admin_credentials_fails(
        self, relations_ready
    ):
        relations_ready.return_value = False
        action_event = Mock()
        self.harness.charm._on_get_admin_credentials(action_event)
        self.assertEqual(
            action_event.fail.call_args,
            [("Relations aren't yet set up. Please try again in a few minutes",)],
        )

    @patch("charm.MagmaNmsMagmalteCharm._relations_ready", new_callable=PropertyMock)
    @patch("charm.MagmaNmsMagmalteCharm._get_admin_username")
    @patch("charm.MagmaNmsMagmalteCharm._get_admin_password")
    @patch("ops.charm.ActionEvent")
    def test_given_juju_action_when_relation_is_realized_then_get_admin_credentials_returns_values(
        self, action_event, _get_admin_password, _get_admin_username, relations_ready
    ):
        relations_ready.return_value = True
        _get_admin_password.return_value = "password"
        _get_admin_username.return_value = "username"
        self.harness.charm._on_get_admin_credentials(action_event)
        self.assertEqual(
            action_event.set_results.call_args,
            [({"admin-username": "username", "admin-password": "password"},)],
        )
