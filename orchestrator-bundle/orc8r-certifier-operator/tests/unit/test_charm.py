# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, PropertyMock, patch

from ops.testing import Harness
from pgconnstr import ConnectionString  # type: ignore[import]

from charm import MagmaOrc8rCertifierCharm


class TestCharm(unittest.TestCase):

    TEST_DB_NAME = MagmaOrc8rCertifierCharm.DB_NAME
    TEST_DB_PORT = "1234"
    TEST_DB_CONNECTION_STRING = ConnectionString(
        "dbname=test_db_name "
        "fallback_application_name=whatever "
        "host=123.456.789.012 "
        "password=aaaBBBcccDDDeee "
        "port=1234 "
        "user=test_db_user"
    )

    @patch("charm.KubernetesServicePatch", lambda charm, ports, additional_labels: None)
    def setUp(self):
        self.harness = Harness(MagmaOrc8rCertifierCharm)
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

    def test_given_initial_status_when_get_pebble_plan_then_content_is_empty(self):
        initial_plan = self.harness.get_container_pebble_plan("magma-orc8r-certifier")
        self.assertEqual(initial_plan.to_yaml(), "{}\n")

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
        with patch.object(MagmaOrc8rCertifierCharm, "DB_NAME", self.TEST_DB_NAME):
            db_event = self._fake_db_event(
                postgres_db_name,
                postgres_username,
                postgres_password,
                postgres_host,
                postgres_port,
            )
            self.harness.charm._on_database_relation_joined(db_event)
        self.assertEqual(db_event.database, self.TEST_DB_NAME)

    @patch("charm.MagmaOrc8rCertifierCharm._namespace", new_callable=PropertyMock)
    @patch("charm.MagmaOrc8rCertifierCharm._db_relation_created")
    @patch("charm.MagmaOrc8rCertifierCharm._db_relation_established")
    def test_given_ready_when_get_plan_then_plan_is_filled_with_magma_orc8r_certifier_service_content(  # noqa: E501
        self, db_relation_established, db_relation_created, patch_namespace
    ):
        namespace = "whatever"
        db_relation_established.return_value = True
        db_relation_created.return_value = True
        patch_namespace.return_value = namespace
        event = Mock()
        with patch(
            "charm.MagmaOrc8rCertifierCharm._get_db_connection_string", new_callable=PropertyMock
        ) as get_db_connection_string:
            get_db_connection_string.return_value = self.TEST_DB_CONNECTION_STRING
            self.harness.charm.on.magma_orc8r_certifier_pebble_ready.emit(event)
            expected_plan = {
                "services": {
                    "magma-orc8r-certifier": {
                        "override": "replace",
                        "startup": "enabled",
                        "command": "/usr/bin/envdir "
                        "/var/opt/magma/envdir "
                        "/var/opt/magma/bin/certifier "
                        "-cac=/var/opt/magma/certs/certifier.pem "
                        "-cak=/var/opt/magma/certs/certifier.key "
                        "-vpnc=/var/opt/magma/certs/vpn_ca.crt "
                        "-vpnk=/var/opt/magma/certs/vpn_ca.key "
                        "-logtostderr=true "
                        "-v=0",
                        "environment": {
                            "DATABASE_SOURCE": f"dbname={self.TEST_DB_NAME} "
                            f"user={self.TEST_DB_CONNECTION_STRING.user} "
                            f"password={self.TEST_DB_CONNECTION_STRING.password} "
                            f"host={self.TEST_DB_CONNECTION_STRING.host} "
                            f"sslmode=disable",
                            "SQL_DRIVER": "postgres",
                            "SQL_DIALECT": "psql",
                            "SERVICE_HOSTNAME": "magma-orc8r-certifier",
                            "SERVICE_REGISTRY_MODE": "k8s",
                            "SERVICE_REGISTRY_NAMESPACE": namespace,
                        },
                    }
                },
            }
            updated_plan = self.harness.get_container_pebble_plan(
                "magma-orc8r-certifier"
            ).to_dict()
            self.assertEqual(expected_plan, updated_plan)

    def test_given_charm_when_remove_event_emitted_then_on_remove_action_called(self):
        with patch.object(MagmaOrc8rCertifierCharm, "_on_remove") as mock:
            self.harness.charm.on.remove.emit()
        mock.assert_called_once()
