# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from typing import Optional, Tuple
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from ops import testing
from ops.model import ActiveStatus, WaitingStatus

from charm import MagmaOrc8rBootstrapperCharm

testing.SIMULATE_CAN_CONNECT = True


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

    @patch("ops.model.Container.exists")
    def test_given_private_key_not_stored_when_pebble_ready_then_status_is_waiting(  # noqa: E501
        self, patch_exists
    ):
        patch_exists.return_value = False
        self.create_peer_relation_with_private_key(bootstrapper_private_key=False)

        self.harness.container_pebble_ready(container_name="magma-orc8r-bootstrapper")

        self.assertEqual(
            self.harness.charm.unit.status,
            WaitingStatus("Waiting for bootstrapper private key to be stored"),
        )

    @patch("ops.model.Container.exec", new=Mock())
    @patch("ops.model.Container.exists")
    def test_given_private_key_is_stored_when_pebble_ready_then_pebble_plan_is_filled_with_workload_service_content(  # noqa: E501
        self, patch_file_exists
    ):
        patch_file_exists.return_value = True
        self.create_peer_relation_with_private_key(bootstrapper_private_key=True)

        self.harness.container_pebble_ready(container_name="magma-orc8r-bootstrapper")
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
                        "SERVICE_REGISTRY_MODE": "k8s",
                        "SERVICE_REGISTRY_NAMESPACE": self.namespace,
                    },
                },
            },
        }

        updated_plan = self.harness.get_container_pebble_plan("magma-orc8r-bootstrapper").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    @patch("ops.model.Container.exec", new=Mock())
    @patch("ops.model.Container.exists")
    def test_given_private_key_is_stored_when_pebble_ready_then_unit_status_is_active(
        self, patch_file_exists
    ):
        patch_file_exists.return_value = True
        self.create_peer_relation_with_private_key(bootstrapper_private_key=True)

        self.harness.container_pebble_ready(container_name="magma-orc8r-bootstrapper")

        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())

    @patch("ops.model.Container.get_service", new=Mock())
    def test_given_magma_orc8r_bootstrapper_service_running_when_magma_orc8r_bootstrapper_relation_joined_event_emitted_then_active_key_in_relation_data_is_set_to_true(  # noqa: E501
        self,
    ):
        container = self.harness.model.unit.get_container("magma-orc8r-bootstrapper")
        self.harness.set_can_connect(container=container, val=True)
        self.harness.set_leader(True)
        relation_id = self.harness.add_relation("magma-orc8r-bootstrapper", "orc8r-bootstrapper")

        self.harness.add_relation_unit(relation_id, "magma-orc8r-bootstrapper/0")

        self.assertEqual(
            self.harness.get_relation_data(relation_id, "magma-orc8r-bootstrapper/0"),
            {"active": "True"},
        )

    @patch("ops.model.Container.get_service", new=Mock())
    def test_given_magma_orc8r_bootstrapper_service_not_running_when_magma_orc8r_bootstrapper_relation_joined_event_emitted_then_active_key_in_relation_data_is_set_to_false(  # noqa: E501
        self,
    ):
        container = self.harness.model.unit.get_container("magma-orc8r-bootstrapper")
        self.harness.set_can_connect(container=container, val=False)
        self.harness.set_leader(True)
        relation_id = self.harness.add_relation("magma-orc8r-bootstrapper", "orc8r-bootstrapper")

        self.harness.add_relation_unit(relation_id, "magma-orc8r-bootstrapper/0")

        self.assertEqual(
            self.harness.get_relation_data(relation_id, "magma-orc8r-bootstrapper/0"),
            {"active": "False"},
        )

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
