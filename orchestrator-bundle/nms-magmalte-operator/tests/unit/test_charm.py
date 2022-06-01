# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, call, patch

from ops import testing
from ops.model import ActiveStatus, BlockedStatus
from pgconnstr import ConnectionString  # type: ignore[import]

from charm import MagmaNmsMagmalteCharm

testing.SIMULATE_CAN_CONNECT = True


class MockExec:
    def exec(self, *args, **kwargs):
        pass

    def wait_output(self, *args, **kwargs):
        pass


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
        self.model_name = "whatever"
        self.harness = testing.Harness(MagmaNmsMagmalteCharm)
        self.harness.set_model_name(name=self.model_name)
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

    def test_given_no_relations_established_when_pebble_ready_then_status_is_blocked(self):
        event = Mock()

        self.harness.charm.on.magma_nms_magmalte_pebble_ready.emit(event)

        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for relation(s) to be created: certificates, db"),
        )

    def test_given_certificates_relation_is_established_and_db_relation_is_missing_when_pebble_ready_then_status_is_blocked(  # noqa: E501
        self,
    ):
        event = Mock()
        relation_id = self.harness.add_relation("certificates", "orc8r-certifier")
        self.harness.add_relation_unit(relation_id, "orc8r-certifier/0")

        self.harness.charm.on.magma_nms_magmalte_pebble_ready.emit(event)

        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for relation(s) to be created: db"),
        )

    @patch("ops.model.Unit.is_leader")
    def test_given_pod_is_leader_when_database_relation_joined_event_then_database_is_set_correctly(  # noqa: E501
        self,
        _,
    ):
        db_event = self._fake_db_event(
            postgres_db_name=self.TEST_DB_NAME,
            postgres_username="yeast",
            postgres_password="water",
            postgres_host="bread",
            postgres_port=self.TEST_DB_PORT,
        )
        self.harness.charm._on_database_relation_joined(db_event)

        self.assertEqual(db_event.database, self.TEST_DB_NAME)

    @patch("pgsql.opslib.pgsql.client.PostgreSQLClient._on_joined")
    @patch("ops.model.Container.exec")
    @patch("ops.model.Container.exists")
    def test_given_relations_are_ready_when_pebble_ready_then_pebble_plan_is_filled_with_magma_nms_magmalte_service_content(  # noqa: E501
        self, patch_file_exists, mock_exec, _
    ):
        certificates_relation_id = self.harness.add_relation(
            relation_name="certificates", remote_app="icey-vault-k8s"
        )
        db_relation_id = self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        self.harness.add_relation_unit(
            relation_id=certificates_relation_id, remote_unit_name="icey-vault-k8s/0"
        )
        self.harness.add_relation_unit(
            relation_id=db_relation_id, remote_unit_name="postgresql-k8s/0"
        )
        key_values = {"master": self.TEST_DB_CONNECTION_STRING}
        self.harness.update_relation_data(
            relation_id=db_relation_id, app_or_unit="postgresql-k8s", key_values=key_values
        )
        mock_exec.return_value = MockExec()
        patch_file_exists.return_value = True

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
                        "API_HOST": f"orc8r-nginx-proxy.{self.model_name}.svc.cluster.local",
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

    @patch("pgsql.opslib.pgsql.client.PostgreSQLClient._on_joined")
    @patch("ops.model.Container.exec")
    @patch("ops.model.Container.exists")
    def test_given_relations_are_established_when_pebble_ready_then_charm_goes_to_active_state(  # noqa: E501
        self, patch_file_exists, mock_exec, _
    ):
        certificates_relation_id = self.harness.add_relation(
            relation_name="certificates", remote_app="icey-vault-k8s"
        )
        db_relation_id = self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        self.harness.add_relation_unit(
            relation_id=certificates_relation_id, remote_unit_name="icey-vault-k8s/0"
        )
        self.harness.add_relation_unit(
            relation_id=db_relation_id, remote_unit_name="postgresql-k8s/0"
        )
        key_values = {"master": "whatever"}
        self.harness.update_relation_data(
            relation_id=db_relation_id, app_or_unit="postgresql-k8s", key_values=key_values
        )
        patch_file_exists.return_value = True
        mock_exec.return_value = MockExec()

        self.harness.container_pebble_ready(container_name="magma-nms-magmalte")

        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())

    @patch(
        "charms.tls_certificates_interface.v0.tls_certificates.InsecureCertificatesRequires.request_certificate"  # noqa: E501,W505
    )
    def test_given_correct_domain_when_certificates_relation_joined_then_certificates_are_requested(  # noqa: E501
        self, patch_request_certificates
    ):
        common_name = "admin_operator"
        relation_id = self.harness.add_relation(
            relation_name="certificates", remote_app="whatever app"
        )

        self.harness.add_relation_unit(
            relation_id=relation_id, remote_unit_name="whatever unit name"
        )

        calls = [call(cert_type="server", common_name=common_name)]
        patch_request_certificates.assert_has_calls(calls)

    @patch("ops.model.Container.push")
    def test_given_pebble_ready_when_certificate_available_then_certificate_and_key_are_pushed_to_workload(  # noqa: E501
        self, patch_push
    ):
        common_name = "admin_operator"
        certificate = "whatever certificate"
        private_key = "whatever private key"
        self.harness.container_pebble_ready("magma-nms-magmalte")
        event = Mock()
        event.certificate_data = {
            "common_name": common_name,
            "cert": certificate,
            "key": private_key,
        }

        self.harness.charm._on_certificate_available(event)

        calls = [
            call("/run/secrets/admin_operator.pem", certificate),
            call("/run/secrets/admin_operator.key.pem", private_key),
        ]
        patch_push.assert_has_calls(calls)
