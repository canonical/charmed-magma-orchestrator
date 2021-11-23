# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, PropertyMock, patch

from ops.model import ActiveStatus, BlockedStatus
from ops.testing import Harness
from pgconnstr import ConnectionString  # type: ignore[import]

from charm import MagmaNmsMagmalteCharm


class TestCharm(unittest.TestCase):
    TEST_DB_NAME = "wheat"
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

    @patch("charm.KubernetesServicePatch", lambda x, y: None)
    def setUp(self):
        self.harness = Harness(MagmaNmsMagmalteCharm)
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

    def test_given_initial_status_when_get_pebble_plan_then_content_is_empty(self):
        initial_plan = self.harness.get_container_pebble_plan("magma-nms-magmalte")
        self.assertEqual(initial_plan.to_yaml(), "{}\n")

    def test_given_charm_when_pebble_ready_event_emitted_and_no_relations_established_then_charm_goes_to_blocked_state(  # noqa: E501
        self,
    ):
        event = Mock()
        self.harness.charm.on.magma_nms_magmalte_pebble_ready.emit(event)
        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for relations: certifier, db"),
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
            BlockedStatus("Waiting for relations: db"),
        )

    @patch("ops.model.Unit.is_leader")
    def test_given_pod_is_leader_when_database_relation_joined_event_then_database_is_set_correctly(  # noqa: E501
        self, is_leader
    ):
        is_leader.return_value = True
        postgres_db_name = self.TEST_DB_NAME
        postgres_host = "bread"
        postgres_password = "water"
        postgres_username = "yeast"
        postgres_port = self.TEST_DB_PORT
        with patch.object(MagmaNmsMagmalteCharm, "DB_NAME", self.TEST_DB_NAME):
            db_event = self._fake_db_event(
                postgres_db_name,
                postgres_username,
                postgres_password,
                postgres_host,
                postgres_port,
            )
            self.harness.charm._on_database_relation_joined(db_event)
        self.assertEqual(db_event.database, self.TEST_DB_NAME)

    @patch("charm.MagmaNmsMagmalteCharm._relations_ready")
    def test_given_ready_when_get_plan_then_plan_is_filled_with_magma_nms_magmalte_service_content(
        self, relations_ready
    ):
        event = Mock()
        relations_ready.return_value = True
        with patch(
            "charm.MagmaNmsMagmalteCharm._get_domain_name", new_callable=PropertyMock
        ) as get_domain_name, patch(
            "charm.MagmaNmsMagmalteCharm._get_db_connection_string", new_callable=PropertyMock
        ) as get_db_connection_string:
            get_domain_name.return_value = self.TEST_DOMAIN_NAME
            get_db_connection_string.return_value = self.TEST_DB_CONNECTION_STRING
            self.harness.charm.on.magma_nms_magmalte_pebble_ready.emit(event)
            expected_plan = {
                "services": {
                    "magma-nms-magmalte": {
                        "startup": "enabled",
                        "override": "replace",
                        "command": "yarn run start:prod",
                        "environment": {
                            "API_CERT_FILENAME": "/run/secrets/admin_operator.pem",
                            "API_PRIVATE_KEY_FILENAME": "/run/secrets/admin_operator.key.pem",
                            "API_HOST": f"api.{self.TEST_DOMAIN_NAME}",
                            "PORT": 8081,
                            "HOST": "0.0.0.0",
                            "MYSQL_HOST": self.TEST_DB_CONNECTION_STRING.host,
                            "MYSQL_PORT": self.TEST_DB_CONNECTION_STRING.port,
                            "MYSQL_DB": self.TEST_DB_CONNECTION_STRING.dbname,
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

    @patch("charm.MagmaNmsMagmalteCharm._relations_ready")
    def test_given_charm_when_pebble_ready_event_emitted_and_relations_are_established_configure_pebble_action_is_called(  # noqa: E501
        self, relations_ready
    ):
        relations_ready.return_value = True
        event = Mock()
        with patch.object(MagmaNmsMagmalteCharm, "_configure_pebble") as mock:
            self.harness.charm.on.magma_nms_magmalte_pebble_ready.emit(event)
        mock.assert_called_once()

    @patch("charm.MagmaNmsMagmalteCharm._relations_ready")
    def test_given_charm_when_pebble_ready_event_emitted_and_relations_are_established_then_charm_goes_to_active_state(  # noqa: E501
        self, relations_ready
    ):
        event = Mock()
        relations_ready.return_value = True
        with patch(
            "charm.MagmaNmsMagmalteCharm._get_domain_name", new_callable=PropertyMock
        ) as get_domain_name, patch(
            "charm.MagmaNmsMagmalteCharm._get_db_connection_string", new_callable=PropertyMock
        ) as get_db_connection_string:
            get_domain_name.return_value = self.TEST_DOMAIN_NAME
            get_db_connection_string.return_value = self.TEST_DB_CONNECTION_STRING
            self.harness.charm.on.magma_nms_magmalte_pebble_ready.emit(event)
            self.assertEqual(self.harness.charm.unit.status, ActiveStatus())
