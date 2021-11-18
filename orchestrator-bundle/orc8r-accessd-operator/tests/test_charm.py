# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, patch

from ops.model import ActiveStatus
from ops.testing import Harness

from charm import MagmaOrc8rAccessdCharm


class TestCharm(unittest.TestCase):

    TEST_DB_NAME = "wheat"
    TEST_DB_PORT = "1234"

    @patch("charm.KubernetesServicePatch", lambda x, y: None)
    def setUp(self):
        self.harness = Harness(MagmaOrc8rAccessdCharm)
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
        initial_plan = self.harness.get_container_pebble_plan("magma-orc8r-accessd")
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
        with patch.object(MagmaOrc8rAccessdCharm, "DB_NAME", self.TEST_DB_NAME):
            db_event = self._fake_db_event(
                postgres_db_name,
                postgres_username,
                postgres_password,
                postgres_host,
                postgres_port,
            )
            self.harness.charm._on_database_relation_joined(db_event)
        self.assertEqual(db_event.database, self.TEST_DB_NAME)

    @patch("ops.model.Unit.is_leader")
    def test_given_ready_when_get_plan_then_plan_is_filled_with_magma_orc8r_accessd_service_content(  # noqa E501
        self, mock_is_leader
    ):
        mock_is_leader.return_value = True
        postgres_db_name = self.TEST_DB_NAME
        postgres_host = "bread"
        postgres_password = "water"
        postgres_username = "yeast"
        postgres_port = self.TEST_DB_PORT
        expected_plan = {
            "services": {
                "magma-orc8r-accessd": {
                    "startup": "enabled",
                    "summary": "magma-orc8r-accessd",
                    "override": "replace",
                    "command": "/usr/bin/envdir "
                    "/var/opt/magma/envdir "
                    "/var/opt/magma/bin/accessd "
                    "-logtostderr=true "
                    "-v=0",
                    "environment": {
                        "DATABASE_SOURCE": f"dbname={postgres_db_name} "
                        f"user={postgres_username} "
                        f"password={postgres_password} "
                        f"host={postgres_host} "
                        f"sslmode=disable",
                        "SQL_DRIVER": "postgres",
                        "SQL_DIALECT": "psql",
                        "SERVICE_HOSTNAME": "magma-orc8r-accessd",
                        "SERVICE_REGISTRY_MODE": "k8s",
                        "HELM_RELEASE_NAME": "orc8r",
                        "SERVICE_REGISTRY_NAMESPACE": "orc8r",
                    },
                },
            },
        }
        db_event = self._fake_db_event(
            postgres_db_name,
            postgres_username,
            postgres_password,
            postgres_host,
            postgres_port,
        )
        self.harness.charm._on_database_relation_joined(db_event)
        updated_plan = self.harness.get_container_pebble_plan("magma-orc8r-accessd").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    @patch("ops.model.Unit.is_leader")
    def test_db_relation_added_when_get_status_then_status_is_active(self, mock_is_leader):
        postgres_db_name = self.TEST_DB_NAME
        postgres_host = "oatmeal"
        postgres_password = "bread"
        postgres_username = "wheat"
        postgres_port = self.TEST_DB_PORT
        mock_is_leader.return_value = True
        db_event = self._fake_db_event(
            postgres_db_name,
            postgres_username,
            postgres_password,
            postgres_host,
            postgres_port,
        )
        self.harness.charm._on_database_relation_joined(db_event)
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())
