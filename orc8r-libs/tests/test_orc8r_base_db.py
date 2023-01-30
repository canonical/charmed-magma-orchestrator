# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, PropertyMock, patch

from charms.magma_orc8r_libs.v0.orc8r_base_db import Orc8rBase
from ops import testing
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from pgconnstr import ConnectionString  # type: ignore[import]
from test_orc8r_base_db_charm.src.charm import (  # type: ignore[import]
    MagmaOrc8rDummyCharm,
)


class TestCharm(unittest.TestCase):

    TEST_DB_NAME = Orc8rBase.DB_NAME
    TEST_DB_PORT = "1234"
    TEST_DB_CONNECTION_STRING = ConnectionString(
        "dbname=test_db_name "
        "fallback_application_name=whatever "
        "host=123.456.789.012 "
        "password=aaaBBBcccDDDeee "
        "port=1234 "
        "user=test_db_user"
    )

    @patch(
        "test_orc8r_base_db_charm.src.charm.KubernetesServicePatch",
        lambda charm, ports, additional_labels: None,
    )
    def setUp(self):
        self.harness = testing.Harness(MagmaOrc8rDummyCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.set_leader(True)
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
        with patch.object(Orc8rBase, "DB_NAME", self.TEST_DB_NAME):
            db_event = self._fake_db_event(
                postgres_db_name,
                postgres_username,
                postgres_password,
                postgres_host,
                postgres_port,
            )
            self.harness.charm._orc8r_base._on_database_relation_joined(db_event)
        self.assertEqual(db_event.database, self.TEST_DB_NAME)

    @patch("psycopg2.connect", new=Mock())
    @patch(
        "charms.magma_orc8r_libs.v0.orc8r_base_db.Orc8rBase.namespace", new_callable=PropertyMock
    )
    def test_given_ready_when_get_plan_then_plan_is_filled_with_magma_orc8r_dummy_service_content(  # noqa: E501
        self,
        patch_namespace,
    ):
        namespace = "whatever"
        db_relation_id = self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        key_values = {"master": self.TEST_DB_CONNECTION_STRING.__str__()}
        self.harness.update_relation_data(
            relation_id=db_relation_id, key_values=key_values, app_or_unit="postgresql-k8s"
        )
        patch_namespace.return_value = namespace

        self.harness.container_pebble_ready("magma-orc8r-dummy")

        expected_plan = {
            "services": {
                "magma-orc8r-dummy": {
                    "startup": "enabled",
                    "summary": "magma-orc8r-dummy",
                    "override": "replace",
                    "command": "/usr/bin/envdir "
                    "/var/opt/magma/envdir "
                    "/var/opt/magma/bin/dummy "
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
                        "SERVICE_HOSTNAME": "magma-orc8r-dummy",
                        "SERVICE_REGISTRY_MODE": "k8s",
                        "SERVICE_REGISTRY_NAMESPACE": namespace,
                    },
                },
            },
        }
        updated_plan = self.harness.get_container_pebble_plan("magma-orc8r-dummy").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    @patch("psycopg2.connect", new=Mock())
    def test_db_relation_added_when_get_status_then_status_is_active(
        self,
    ):
        db_relation_id = self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        key_values = {"master": self.TEST_DB_CONNECTION_STRING.__str__()}
        self.harness.update_relation_data(
            relation_id=db_relation_id, key_values=key_values, app_or_unit="postgresql-k8s"
        )

        self.harness.container_pebble_ready("magma-orc8r-dummy")

        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())

    def test_given_db_relation_not_created_when_pebble_ready_then_status_is_blocked(
        self,
    ):
        self.harness.container_pebble_ready(container_name="magma-orc8r-dummy")
        assert self.harness.charm.unit.status == BlockedStatus(
            "Waiting for db relation to be created"
        )

    def test_given_db_relation_not_ready_when_pebble_ready_then_status_is_blocked(self):
        self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        self.harness.container_pebble_ready(container_name="magma-orc8r-dummy")
        assert self.harness.charm.unit.status == WaitingStatus(
            "Waiting for db relation to be ready"
        )

    @patch("psycopg2.connect", new=Mock())
    @patch(
        "charms.magma_orc8r_libs.v0.orc8r_base_db.Orc8rBase.namespace",
        PropertyMock(return_value="qwerty"),
    )
    def test_given_pebble_ready_when_db_relation_broken_then_status_is_blocked(
        self,
    ):
        self.harness.set_can_connect("magma-orc8r-dummy", True)
        container = self.harness.model.unit.get_container("magma-orc8r-dummy")
        db_relation_id = self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        key_values = {"master": self.TEST_DB_CONNECTION_STRING.__str__()}
        self.harness.update_relation_data(
            relation_id=db_relation_id, key_values=key_values, app_or_unit="postgresql-k8s"
        )
        self.harness.charm.on.magma_orc8r_dummy_pebble_ready.emit(container)
        assert self.harness.charm.unit.status == ActiveStatus()

        self.harness.remove_relation(db_relation_id)

        assert self.harness.charm.unit.status == BlockedStatus(
            "Waiting for db relation to be created"
        )

    @patch("psycopg2.connect", new=Mock())
    @patch(
        "charms.magma_orc8r_libs.v0.orc8r_base_db.Orc8rBase.namespace",
        PropertyMock(return_value="qwerty"),
    )
    def test_given_magma_orc8r_dummy_service_running_when_metrics_magma_orc8r_dummy_relation_joined_event_emitted_then_active_key_in_relation_data_is_set_to_true(  # noqa: E501
        self,
    ):
        db_relation_id = self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        key_values = {"master": self.TEST_DB_CONNECTION_STRING.__str__()}
        self.harness.update_relation_data(
            relation_id=db_relation_id, key_values=key_values, app_or_unit="postgresql-k8s"
        )
        self.harness.set_can_connect("magma-orc8r-dummy", True)
        container = self.harness.model.unit.get_container("magma-orc8r-dummy")
        self.harness.charm.on.magma_orc8r_dummy_pebble_ready.emit(container)
        relation_id = self.harness.add_relation("magma-orc8r-dummy", "orc8r-dummy")
        self.harness.add_relation_unit(relation_id, "magma-orc8r-dummy/0")

        self.assertEqual(
            self.harness.get_relation_data(relation_id, "magma-orc8r-dummy/0"),
            {"active": "True"},
        )

    @patch(
        "charms.magma_orc8r_libs.v0.orc8r_base_db.Orc8rBase.namespace",
        PropertyMock(return_value="qwerty"),
    )
    def test_given_magma_orc8r_dummy_service_not_running_when_magma_orc8r_dummy_relation_joined_event_emitted_then_active_key_in_relation_data_is_set_to_false(  # noqa: E501
        self,
    ):
        relation_id = self.harness.add_relation("magma-orc8r-dummy", "orc8r-dummy")
        self.harness.add_relation_unit(relation_id, "magma-orc8r-dummy/0")

        self.assertEqual(
            self.harness.get_relation_data(relation_id, "magma-orc8r-dummy/0"),
            {"active": "False"},
        )
