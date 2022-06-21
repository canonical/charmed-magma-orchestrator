# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, PropertyMock, patch

from ops import testing
from ops.model import ActiveStatus, BlockedStatus
from pgconnstr import ConnectionString  # type: ignore[import]

from charm import MagmaOrc8rBootstrapperCharm

testing.SIMULATE_CAN_CONNECT = True

class TestCharm(unittest.TestCase):
    
    TEST_DB_NAME = MagmaOrc8rBootstrapperCharm.DB_NAME
    TEST_DB_PORT = "1234"
    TEST_DB_CONNECTION_STRING = ConnectionString(
        "dbname=test_db_name "
        "fallback_application_name=whatever "
        "host=123.456.789.101 "
        "password=test-password"
        "port=1234"
        "user=test_user"
    )

    @patch("charm.KubernetesServicePatch", lambda charm, ports, additional_labels: None)
    def setUp(self):
        self.harness = testing.Harness(MagmaOrc8rBootstrapperCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.maxDiff = None
    
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
        self.harness.charm.on.magma_orc8r_bootstrapper_pebble_ready.emit(event)
        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for orc8r-certifier relation..."),
        )

    @patch("charm.MagmaOrc8rBootstrapperCharm._get_db_connection_string", new_callable=PropertyMock)
    @patch("charm.MagmaOrc8rBootstrapperCharm._namespace", new_callable=PropertyMock)
    @patch("charm.MagmaOrc8rBootstrapperCharm._orc8r_certs_mounted")
    @patch("charm.MagmaOrc8rBootstrapperCharm._certifier_relation_ready")
    def test_given_ready_when_get_plan_then_plan_is_filled_with_magma_orc8r_bootstrapper_service_content(  # noqa: E501
        self, certifier_relation_ready, orc8r_certs_mounted, patch_namespace,get_db_connection_string
    ):
        namespace = "whatever"
        certifier_relation_ready.return_value = True
        orc8r_certs_mounted.return_value = True
        patch_namespace.return_value = namespace
        get_db_connection_string.return_value = self.TEST_DB_CONNECTION_STRING
        expected_plan = {
            "services": {
                "magma-orc8r-bootstrapper": {
                    "override": "replace",
                    "startup": "enabled",
                    "command": "/usr/bin/envdir "
                    "/var/opt/magma/envdir "
                    "/var/opt/magma/bin/bootstrapper "
                    "-cak=/var/opt/magma/certs/bootstrapper.key "
                    "-logtostderr=true "
                    "-v=0",
                    "environment": {
                        "SERVICE_HOSTNAME": "magma-orc8r-bootstrapper",
                        "SERVICE_REGISTRY_MODE": "k8s",
                        "SERVICE_REGISTRY_NAMESPACE": namespace,
                        "DATABASE_SOURCE": f"dbname={self.TEST_DB_NAME} "
                        f"user={self.TEST_DB_CONNECTION_STRING.user} "
                        f"password={self.TEST_DB_CONNECTION_STRING.password} "
                        f"host={self.TEST_DB_CONNECTION_STRING.host} "
                        f"port={self.TEST_DB_CONNECTION_STRING.port} "
                        f"sslmode=disable",
                        "SQL_DRIVER": "postgres",
                        "SQL_DIALECT": "psql",
                    },
                },
            },
        }
        self.harness.container_pebble_ready("magma-orc8r-bootstrapper")
        updated_plan = self.harness.get_container_pebble_plan("magma-orc8r-bootstrapper").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    @patch("ops.model.Unit.is_leader")
    def test_given_pod_is_leader_when_database_relation_joined_event_then_database_is_set_correctly(  # noqa: E501
        self, is_leader
    ):
        is_leader.return_value = True
        postgres_db_name = self.TEST_DB_NAME
        postgres_host = "test_host"
        postgres_password = "password123"
        postgres_username = "test_user"
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
    
    @patch("charm.MagmaOrc8rBootstrapperCharm._orc8r_certs_mounted")
    def test_given_charm_when_pebble_ready_event_emitted_and_certifier_relation_is_established_and_certs_mounted_but_db_relation_is_missing_then_charm_goes_to_blocked_state(  # noqa: E501
        self, mock_orc8r_certs_mounted
    ):
        event = Mock()
        relation_id = self.harness.add_relation("certifier", "orc8r-certifier")
        self.harness.add_relation_unit(relation_id, "orc8r-certifier/0")
      
        
        mock_orc8r_certs_mounted.return_value=True
        
        self.harness.charm.on.magma_orc8r_bootstrapper_pebble_ready.emit(event)

        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for database relation to be established"),
        )

    @patch("charm.MagmaOrc8rBootstrapperCharm._on_certifier_relation_joined")
    def test_given_charm_when_certifier_relation_added_then_on_certifier_relation_joined_action_called(  # noqa: E501
        self, mock_on_certifier_relation_joined
    ):
        relation_id = self.harness.add_relation("certifier", "orc8r-certifier")
        self.harness.add_relation_unit(relation_id, "orc8r-certifier/0")

        self.harness.update_relation_data(relation_id, "orc8r-certifier/0", {})

        mock_on_certifier_relation_joined.assert_called_once()


    @patch("charm.MagmaOrc8rBootstrapperCharm._orc8r_certs_mounted")
    @patch("charm.MagmaOrc8rBootstrapperCharm._get_db_connection_string", new_callable=PropertyMock)
    @patch("charm.MagmaOrc8rBootstrapperCharm._configure_pebble")
    def test_given_charm_when_pebble_ready_event_emitted_and_relations_are_established_and_certs_mounted_configure_pebble_is_called(  # noqa: E501
        self, mock_configure_pebble, get_db_connection_string, mock_orc8r_certs_mounted, 
    ):
        relation_id = self.harness.add_relation("certifier", "orc8r-certifier")
        self.harness.add_relation_unit(relation_id, "orc8r-certifier/0")

        mock_orc8r_certs_mounted.return_value=True
        get_db_connection_string.return_value = self.TEST_DB_CONNECTION_STRING
       
        event=Mock()
        self.harness.charm.on.magma_orc8r_bootstrapper_pebble_ready.emit(event)

        mock_configure_pebble.assert_called_once()

    @patch("charm.MagmaOrc8rBootstrapperCharm._orc8r_certs_mounted")
    @patch("charm.MagmaOrc8rBootstrapperCharm._get_db_connection_string", new_callable=PropertyMock)
    def test_given_charm_when_pebble_ready_event_emitted_and_relations_are_established_and_certs_mounted_then_charm_goes_to_active_state(  # noqa: E501
        self, get_db_connection_string, mock_orc8r_certs_mounted
    ):
        mock_orc8r_certs_mounted.return_value=True
        relation_id = self.harness.add_relation("certifier", "orc8r-certifier")
        self.harness.add_relation_unit(relation_id, "orc8r-certifier/0")
        get_db_connection_string.return_value = self.TEST_DB_CONNECTION_STRING
        self.harness.container_pebble_ready(container_name="magma-orc8r-bootstrapper")

        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())