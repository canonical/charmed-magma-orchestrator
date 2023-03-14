# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from typing import Optional, Tuple
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from ops import testing
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from pgconnstr import ConnectionString  # type: ignore[import]

from charm import MagmaOrc8rBootstrapperCharm


def generate_private_key(
    password: Optional[bytes] = None,
    key_size: int = 2048,
    public_exponent: int = 65537,
) -> bytes:
    """Generates a private key.

    Args:
        password (bytes): Password for decrypting the private key
        key_size (int): Key size in bytes
        public_exponent: Public exponent.

    Returns:
        bytes: Private Key
    """
    private_key = rsa.generate_private_key(
        public_exponent=public_exponent,
        key_size=key_size,
    )
    key_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.BestAvailableEncryption(password)
        if password
        else serialization.NoEncryption(),
    )
    return key_bytes


class TestCharm(unittest.TestCase):
    BASE_CERTS_PATH = "/var/opt/magma/certs"
    CERT_ROOT_CA_RELATION = "cert-root-ca"
    TEST_DB_NAME = MagmaOrc8rBootstrapperCharm.DB_NAME
    TEST_DB_PORT = "1234"
    TEST_DB_CONNECTION_STRING = ConnectionString(
        "dbname=test_db_name "
        "fallback_application_name=whatever "
        "host=123.456.789.012 "
        "password=aaaBBBcccDDDeee "
        "port=1234 "
        "user=test_db_user"
    )

    def create_peer_relation_with_private_key(
        self, bootstrapper_private_key: bool = False
    ) -> Tuple[int, dict]:
        """Creates a peer relation and adds certificates in its data.

        Args:
            bootstrapper_private_key: Set bootstrapper private key

        Returns:
            int: Peer relation ID
            dict: Relation data
        """
        key_values = {}
        if bootstrapper_private_key:
            key_values["bootstrapper_private_key"] = generate_private_key().decode()

        peer_relation_id = self.harness.add_relation("replicas", self.harness.charm.app.name)
        self.harness.add_relation_unit(peer_relation_id, self.harness.charm.unit.name)

        self.harness.update_relation_data(
            relation_id=peer_relation_id,
            app_or_unit=self.harness.charm.app.name,
            key_values=key_values,
        )
        return peer_relation_id, key_values

    @patch("charm.KubernetesServicePatch", lambda charm, ports, additional_labels: None)
    def setUp(self):
        self.namespace = "whatever namespace"
        self.harness = testing.Harness(MagmaOrc8rBootstrapperCharm)
        self.harness.set_model_name(name=self.namespace)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.maxDiff = None

    @patch("pgsql.opslib.pgsql.client.PostgreSQLClient._on_joined")
    @patch("ops.model.Container.exists")
    def test_given_private_key_not_stored_when_pebble_ready_then_status_is_waiting(  # noqa: E501
        self, patch_exists, _
    ):
        patch_exists.return_value = True
        self.create_peer_relation_with_private_key(bootstrapper_private_key=False)
        db_relation_id = self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        self.harness.add_relation_unit(
            relation_id=db_relation_id, remote_unit_name="postgresql-k8s/0"
        )
        key_values = {"master": self.TEST_DB_CONNECTION_STRING.__str__()}
        self.harness.update_relation_data(
            relation_id=db_relation_id, app_or_unit="postgresql-k8s", key_values=key_values
        )

        root_ca_relation_id = self.harness.add_relation(
            relation_name="cert-root-ca", remote_app="magma-orc8r-certifier"
        )
        self.harness.add_relation_unit(
            relation_id=root_ca_relation_id, remote_unit_name="magma-orc8r-certifier/0"
        )

        self.harness.container_pebble_ready(container_name="magma-orc8r-bootstrapper")

        self.assertEqual(
            self.harness.charm.unit.status,
            WaitingStatus("Waiting for bootstrapper private key to be stored"),
        )

    @patch("pgsql.opslib.pgsql.client.PostgreSQLClient._on_joined")
    @patch("ops.model.Container.exists")
    def test_given_root_ca_relation_not_created_when_pebble_ready_then_status_is_blocked(  # noqa: E501
        self, patch_exists, _
    ):
        patch_exists.return_value = True
        self.create_peer_relation_with_private_key(bootstrapper_private_key=True)
        db_relation_id = self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        self.harness.add_relation_unit(
            relation_id=db_relation_id, remote_unit_name="postgresql-k8s/0"
        )
        key_values = {"master": self.TEST_DB_CONNECTION_STRING.__str__()}
        self.harness.update_relation_data(
            relation_id=db_relation_id, app_or_unit="postgresql-k8s", key_values=key_values
        )

        self.harness.container_pebble_ready(container_name="magma-orc8r-bootstrapper")

        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus(f"Waiting for {self.CERT_ROOT_CA_RELATION} relation to be created"),
        )

    @patch("pgsql.opslib.pgsql.client.PostgreSQLClient._on_joined")
    @patch("ops.model.Container.exists")
    def test_given_db_relation_not_created_when_pebble_ready_then_status_is_waiting(  # noqa: E501
        self, patch_exists, _
    ):
        patch_exists.return_value = True
        self.create_peer_relation_with_private_key(bootstrapper_private_key=True)

        root_ca_relation_id = self.harness.add_relation(
            relation_name="cert-root-ca", remote_app="magma-orc8r-certifier"
        )
        self.harness.add_relation_unit(
            relation_id=root_ca_relation_id, remote_unit_name="magma-orc8r-certifier/0"
        )

        self.harness.container_pebble_ready(container_name="magma-orc8r-bootstrapper")

        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for database relation to be created"),
        )

    @patch("psycopg2.connect", new=Mock())
    @patch("pgsql.opslib.pgsql.client.PostgreSQLClient._on_joined")
    @patch("ops.model.Container.exists")
    @patch("charm.ConnectionString")
    def test_given_root_ca_not_pushed_when_pebble_ready_then_status_is_waiting(  # noqa: E501
        self, patch_connection_string, patch_exists, _
    ):
        patch_exists.side_effect = lambda s: s != f"{self.BASE_CERTS_PATH}/rootCA.pem"
        self.create_peer_relation_with_private_key(bootstrapper_private_key=True)
        db_relation_id = self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        self.harness.add_relation_unit(
            relation_id=db_relation_id, remote_unit_name="postgresql-k8s/0"
        )
        key_values = {"master": self.TEST_DB_CONNECTION_STRING.__str__()}
        patch_connection_string.return_value = self.TEST_DB_CONNECTION_STRING
        self.harness.update_relation_data(
            relation_id=db_relation_id, app_or_unit="postgresql-k8s", key_values=key_values
        )

        root_ca_relation_id = self.harness.add_relation(
            relation_name="cert-root-ca", remote_app="magma-orc8r-certifier"
        )
        self.harness.add_relation_unit(
            relation_id=root_ca_relation_id, remote_unit_name="magma-orc8r-certifier/0"
        )

        self.harness.container_pebble_ready(container_name="magma-orc8r-bootstrapper")

        self.assertEqual(
            self.harness.charm.unit.status,
            WaitingStatus("Waiting for root ca to be pushed."),
        )

    @patch("ops.model.Container.exec", new=Mock())
    @patch("psycopg2.connect", new=Mock())
    @patch("pgsql.opslib.pgsql.client.PostgreSQLClient._on_joined")
    @patch("ops.model.Container.exists")
    @patch("charm.ConnectionString")
    def test_given_private_key_is_stored_when_pebble_ready_then_pebble_plan_is_filled_with_workload_service_content(  # noqa: E501
        self, patch_connection_string, patch_file_exists, _
    ):
        patch_file_exists.return_value = True

        self.create_peer_relation_with_private_key(bootstrapper_private_key=True)

        db_relation_id = self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        self.harness.add_relation_unit(
            relation_id=db_relation_id, remote_unit_name="postgresql-k8s/0"
        )
        key_values = {"master": self.TEST_DB_CONNECTION_STRING.__str__()}
        patch_connection_string.return_value = self.TEST_DB_CONNECTION_STRING
        self.harness.update_relation_data(
            relation_id=db_relation_id, app_or_unit="postgresql-k8s", key_values=key_values
        )

        root_ca_relation_id = self.harness.add_relation(
            relation_name="cert-root-ca", remote_app="magma-orc8r-certifier"
        )
        self.harness.add_relation_unit(
            relation_id=root_ca_relation_id, remote_unit_name="magma-orc8r-certifier/0"
        )

        self.harness.container_pebble_ready(container_name="magma-orc8r-bootstrapper")
        expected_plan = {
            "services": {
                "magma-orc8r-bootstrapper": {
                    "override": "replace",
                    "startup": "enabled",
                    "command": "bootstrapper "
                    "-cak=/var/opt/magma/certs/bootstrapper.key "
                    "-logtostderr=true "
                    "-v=0",
                    "environment": {
                        "SERVICE_HOSTNAME": "magma-orc8r-bootstrapper",
                        "SERVICE_REGISTRY_MODE": "k8s",
                        "SERVICE_REGISTRY_NAMESPACE": self.namespace,
                        "DATABASE_SOURCE": f"dbname={self.TEST_DB_NAME} "
                        f"user={self.TEST_DB_CONNECTION_STRING.user} "
                        f"password={self.TEST_DB_CONNECTION_STRING.password} "
                        f"host={self.TEST_DB_CONNECTION_STRING.host} "
                        f"port={self.TEST_DB_PORT} "
                        f"sslmode=disable",
                        "SQL_DRIVER": "postgres",
                        "SQL_DIALECT": "psql",
                    },
                },
            },
        }

        updated_plan = self.harness.get_container_pebble_plan("magma-orc8r-bootstrapper").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    @patch("ops.model.Container.exec", new=Mock())
    @patch("psycopg2.connect", new=Mock())
    @patch("pgsql.opslib.pgsql.client.PostgreSQLClient._on_joined")
    @patch("ops.model.Container.exists")
    @patch("charm.ConnectionString")
    def test_given_private_key_is_stored_relations_created_and_root_ca_pushed_when_pebble_ready_then_unit_status_is_active(  # noqa: E501
        self, patch_connection_string, patch_file_exists, _
    ):
        patch_file_exists.return_value = True
        self.create_peer_relation_with_private_key(bootstrapper_private_key=True)

        db_relation_id = self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        self.harness.add_relation_unit(
            relation_id=db_relation_id, remote_unit_name="postgresql-k8s/0"
        )
        key_values = {"master": self.TEST_DB_CONNECTION_STRING.__str__()}
        patch_connection_string.return_value = self.TEST_DB_CONNECTION_STRING
        self.harness.update_relation_data(
            relation_id=db_relation_id, app_or_unit="postgresql-k8s", key_values=key_values
        )

        root_ca_relation_id = self.harness.add_relation(
            relation_name="cert-root-ca", remote_app="magma-orc8r-certifier"
        )
        self.harness.add_relation_unit(
            relation_id=root_ca_relation_id, remote_unit_name="magma-orc8r-certifier/0"
        )

        self.harness.container_pebble_ready(container_name="magma-orc8r-bootstrapper")

        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())

    @patch("charm.pgsql.PostgreSQLClient._mirror_appdata", new=Mock())
    @patch("ops.model.Container.get_service", new=Mock())
    def test_given_magma_orc8r_bootstrapper_service_running_when_magma_orc8r_bootstrapper_relation_joined_event_emitted_then_active_key_in_relation_data_is_set_to_true(  # noqa: E501
        self,
    ):
        container = self.harness.model.unit.get_container("magma-orc8r-bootstrapper")
        self.harness.set_can_connect(container=container, val=True)
        self.harness.set_leader(True)
        relation_id = self.harness.add_relation(
            "magma-orc8r-bootstrapper", "magma-orc8r-bootstrapper"
        )

        self.harness.add_relation_unit(relation_id, "magma-orc8r-bootstrapper/0")

        self.assertEqual(
            self.harness.get_relation_data(relation_id, "magma-orc8r-bootstrapper/0"),
            {"active": "True"},
        )

    @patch("charm.pgsql.PostgreSQLClient._mirror_appdata", new=Mock())
    @patch("ops.model.Container.get_service", new=Mock())
    def test_given_magma_orc8r_bootstrapper_service_not_running_when_magma_orc8r_bootstrapper_relation_joined_event_emitted_then_active_key_in_relation_data_is_set_to_false(  # noqa: E501
        self,
    ):
        container = self.harness.model.unit.get_container("magma-orc8r-bootstrapper")
        self.harness.set_can_connect(container=container, val=False)
        self.harness.set_leader(is_leader=True)
        relation_id = self.harness.add_relation(
            "magma-orc8r-bootstrapper", "magma-orc8r-bootstrapper"
        )

        self.harness.add_relation_unit(relation_id, "magma-orc8r-bootstrapper/0")

        self.assertEqual(
            self.harness.get_relation_data(relation_id, "magma-orc8r-bootstrapper/0"),
            {"active": "False"},
        )

    @patch("charm.pgsql.PostgreSQLClient._mirror_appdata", new=Mock())
    @patch("ops.model.Container.push")
    def test_given_unit_is_leader_and_replicas_relation_is_created_when_on_install_then_bootstrapper_private_key_is_stored(  # noqa: E501
        self, _
    ):
        self.harness.set_leader(is_leader=True)
        self.harness.set_can_connect(container="magma-orc8r-bootstrapper", val=True)
        event = Mock()

        peer_relation_id = self.harness.add_relation("replicas", self.harness.charm.app.name)

        relation_data = self.harness.get_relation_data(
            relation_id=peer_relation_id, app_or_unit=self.harness.charm.app.name
        )

        self.harness.charm._on_install(event=event)

        serialization.load_pem_private_key(
            relation_data["bootstrapper_private_key"].encode(), password=None
        )

    @patch("charm.pgsql.PostgreSQLClient._mirror_appdata", new=Mock())
    @patch("ops.model.Container.push")
    def test_given_unit_is_leader_and_replicas_relation_is_created_when_on_install_then_bootstrapper_private_key_is_pushed_to_workload(  # noqa: E501
        self, patch_push
    ):
        self.harness.set_leader(is_leader=True)
        self.harness.set_can_connect(container="magma-orc8r-bootstrapper", val=True)
        event = Mock()

        peer_relation_id = self.harness.add_relation("replicas", self.harness.charm.app.name)

        self.harness.get_relation_data(
            relation_id=peer_relation_id, app_or_unit=self.harness.charm.app.name
        )

        self.harness.charm._on_install(event=event)

        args, kwargs = patch_push.call_args
        assert kwargs["path"] == "/var/opt/magma/certs/bootstrapper.key"
        serialization.load_pem_private_key(kwargs["source"].encode(), password=None)

    @patch("ops.model.Container.push")
    def test_given_unit_is_not_leader_and_bootstrapper_private_key_is_stored_when_on_install_then_bootstrapper_private_key_is_pushed_to_workload(  # noqa: E501
        self, patch_push
    ):
        self.harness.set_leader(is_leader=False)
        self.harness.set_can_connect(container="magma-orc8r-bootstrapper", val=True)
        event = Mock()

        relation_id, key_values = self.create_peer_relation_with_private_key(
            bootstrapper_private_key=True
        )

        self.harness.charm._on_install(event=event)

        args, kwargs = patch_push.call_args
        assert kwargs["path"] == "/var/opt/magma/certs/bootstrapper.key"
        assert kwargs["source"] == key_values["bootstrapper_private_key"]

    def test_given_unit_is_not_leader_and_bootstrapper_private_key_is_not_stored_when_on_install_then_status_is_waiting(  # noqa: E501
        self,
    ):
        self.harness.set_leader(is_leader=False)
        self.harness.set_can_connect(container="magma-orc8r-bootstrapper", val=True)
        event = Mock()

        self.create_peer_relation_with_private_key(bootstrapper_private_key=False)

        self.harness.charm._on_install(event=event)

        self.assertEqual(
            self.harness.charm.unit.status,
            WaitingStatus("Waiting for leader to generate bootstrapper private key"),
        )
