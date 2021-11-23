# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, PropertyMock, patch

from ops.model import ActiveStatus
from ops.testing import Harness
from pgconnstr import ConnectionString  # type: ignore[import]

from charm import MagmaOrc8rDirectorydCharm


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

    @patch("charm.KubernetesServicePatch", lambda x, y, service_name: None)
    def setUp(self):
        self.harness = Harness(MagmaOrc8rDirectorydCharm)
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
        initial_plan = self.harness.get_container_pebble_plan("magma-orc8r-directoryd")
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
        with patch.object(MagmaOrc8rDirectorydCharm, "DB_NAME", self.TEST_DB_NAME):
            db_event = self._fake_db_event(
                postgres_db_name,
                postgres_username,
                postgres_password,
                postgres_host,
                postgres_port,
            )
            self.harness.charm._on_database_relation_joined(db_event)
        self.assertEqual(db_event.database, self.TEST_DB_NAME)

    @patch("charm.MagmaOrc8rDirectorydCharm._check_db_relation_has_been_established")
    def test_given_ready_when_get_plan_then_plan_is_filled_with_magma_orc8r_directoryd_service_content(  # noqa: E501
        self, db_relation_established
    ):
        event = Mock()
        db_relation_established.return_value = True
        with patch(
            "charm.MagmaOrc8rDirectorydCharm._get_db_connection_string", new_callable=PropertyMock
        ) as get_db_connection_string:
            get_db_connection_string.return_value = self.TEST_DB_CONNECTION_STRING
            self.harness.charm.on.magma_orc8r_directoryd_pebble_ready.emit(event)
        expected_plan = {
            "services": {
                "magma-orc8r-directoryd": {
                    "startup": "enabled",
                    "summary": "magma-orc8r-directoryd",
                    "override": "replace",
                    "command": "/usr/bin/envdir "
                    "/var/opt/magma/envdir "
                    "/var/opt/magma/bin/directoryd "
                    "-logtostderr=true "
                    "-v=0",
                    "environment": {
                        "DATABASE_SOURCE": f"dbname={self.TEST_DB_CONNECTION_STRING.dbname} "
                        f"user={self.TEST_DB_CONNECTION_STRING.user} "
                        f"password={self.TEST_DB_CONNECTION_STRING.password} "
                        f"host={self.TEST_DB_CONNECTION_STRING.host} "
                        f"sslmode=disable",
                        "SQL_DRIVER": "postgres",
                        "SQL_DIALECT": "psql",
                        "SERVICE_HOSTNAME": "magma-orc8r-directoryd",
                        "SERVICE_REGISTRY_MODE": "k8s",
                        "HELM_RELEASE_NAME": "orc8r",
                        "SERVICE_REGISTRY_NAMESPACE": "orc8r",
                    },
                },
            },
        }
        updated_plan = self.harness.get_container_pebble_plan("magma-orc8r-directoryd").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    @patch("charm.MagmaOrc8rDirectorydCharm._check_db_relation_has_been_established")
    def test_db_relation_added_when_get_status_then_status_is_active(
        self, db_relation_established
    ):
        event = Mock()
        db_relation_established.return_value = True
        with patch(
            "charm.MagmaOrc8rDirectorydCharm._get_db_connection_string", new_callable=PropertyMock
        ) as get_db_connection_string:
            get_db_connection_string.return_value = self.TEST_DB_CONNECTION_STRING
            self.harness.charm.on.magma_orc8r_directoryd_pebble_ready.emit(event)
            self.assertEqual(self.harness.charm.unit.status, ActiveStatus())
