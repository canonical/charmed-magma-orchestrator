# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, PropertyMock, patch

from ops import testing
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
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

    def test_given_no_relations_created_when_pebble_ready_event_emitted_then_charm_goes_to_blocked_state(  # noqa: E501
        self,
    ):
        event = Mock()

        self.harness.charm.on.magma_nms_magmalte_pebble_ready.emit(event)

        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for relation(s) to be created: magma-orc8r-certifier, db"),
        )

    def test_given_certifier_relation_created_but_db_relation_missing_when_pebble_ready_event_emitted_then_charm_goes_to_blocked_state(  # noqa: E501
        self,
    ):
        event = Mock()
        relation_id = self.harness.add_relation("magma-orc8r-certifier", "orc8r-certifier")
        self.harness.add_relation_unit(relation_id, "orc8r-certifier/0")

        self.harness.charm.on.magma_nms_magmalte_pebble_ready.emit(event)

        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for relation(s) to be created: db"),
        )

    @patch("charm.MagmaNmsMagmalteCharm._relations_created", PropertyMock(return_value=True))
    def test_given_relations_created_when_pebble_ready_event_emitted_then_charm_goes_to_waiting_state(  # noqa: E501
        self,
    ):
        self.harness.container_pebble_ready(container_name="magma-nms-magmalte")

        self.assertEqual(
            self.harness.charm.unit.status,
            WaitingStatus("Waiting for relation(s) to be ready: magma-orc8r-certifier, db"),
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

    @patch("charm.MagmaNmsMagmalteCharm._get_db_connection_string", new_callable=PropertyMock)
    @patch("charm.MagmaNmsMagmalteCharm._create_master_nms_admin_user", Mock())
    @patch("charm.MagmaNmsMagmalteCharm._namespace", new_callable=PropertyMock)
    @patch("charm.MagmaNmsMagmalteCharm._nms_certs_mounted", PropertyMock(return_value=True))
    @patch("charm.MagmaNmsMagmalteCharm._relations_ready", PropertyMock(return_value=True))
    @patch("charm.MagmaNmsMagmalteCharm._relations_created", PropertyMock(return_value=True))
    def test_given_ready_when_get_plan_then_plan_is_filled_with_magma_nms_magmalte_service_content(
        self, mocked_namespace, mocked_get_db_connection_string
    ):
        namespace = "whatever"
        mocked_namespace.return_value = namespace
        mocked_get_db_connection_string.return_value = self.TEST_DB_CONNECTION_STRING

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

    @patch("charm.MagmaNmsMagmalteCharm._get_db_connection_string", new_callable=PropertyMock)
    @patch("charm.MagmaNmsMagmalteCharm._create_master_nms_admin_user", Mock())
    @patch("charm.MagmaNmsMagmalteCharm._nms_certs_mounted", PropertyMock(return_value=True))
    @patch("charm.MagmaNmsMagmalteCharm._relations_ready", PropertyMock(return_value=True))
    @patch("charm.MagmaNmsMagmalteCharm._relations_created", PropertyMock(return_value=True))
    def test_given_charm_when_pebble_ready_event_emitted_and_relations_are_established_then_charm_goes_to_active_state(  # noqa: E501
        self, mocked_get_db_connection_string
    ):
        mocked_get_db_connection_string.return_value = self.TEST_DB_CONNECTION_STRING
        self.harness.set_can_connect("magma-nms-magmalte", True)
        self.harness.container_pebble_ready(container_name="magma-nms-magmalte")

        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())
