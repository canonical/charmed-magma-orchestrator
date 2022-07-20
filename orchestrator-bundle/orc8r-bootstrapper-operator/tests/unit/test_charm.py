# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, patch

from ops import testing
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

from charm import MagmaOrc8rBootstrapperCharm

testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    @patch("charm.KubernetesServicePatch", lambda charm, ports, additional_labels: None)
    def setUp(self):
        self.namespace = "whatever namespace"
        self.harness = testing.Harness(MagmaOrc8rBootstrapperCharm)
        self.harness.set_model_name(name=self.namespace)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.maxDiff = None

    def test_given_cert_bootstrapper_relation_not_created_when_pebble_ready_status_is_blocked(
        self,
    ):
        self.harness.container_pebble_ready(container_name="magma-orc8r-bootstrapper")

        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for cert-bootstrapper relation to be created"),
        )

    @patch("ops.model.Container.exists")
    def test_given_cert_bootstrapper_relation_created_and_certs_not_stored_when_pebble_ready_status_is_waiting(  # noqa: E501
        self, patch_exists
    ):
        patch_exists.return_value = False
        self.harness.add_relation(
            relation_name="cert-bootstrapper", remote_app="magma-orc8r-certifier"
        )
        self.harness.container_pebble_ready(container_name="magma-orc8r-bootstrapper")

        self.assertEqual(
            self.harness.charm.unit.status,
            WaitingStatus("Waiting for certs to be available"),
        )

    @patch("ops.model.Container.exec", new=Mock())
    @patch("ops.model.Container.exists")
    def test_given_cert_bootstrapper_relation_is_created_and_certs_are_stored_when_pebble_ready_then_pebble_plan_is_filled_with_workload_service_content(  # noqa: E501
        self, patch_file_exists
    ):
        patch_file_exists.return_value = True
        self.harness.add_relation(
            relation_name="cert-bootstrapper", remote_app="magma-orc8r-certifier"
        )

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
    def test_given_bootstrapper_relation_is_created_and_certs_are_stored_when_pebble_ready_then_unit_status_is_active(  # noqa: E501
        self, patch_file_exists
    ):
        patch_file_exists.return_value = True
        self.harness.add_relation(
            relation_name="cert-bootstrapper", remote_app="magma-orc8r-certifier"
        )

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
    def test_given_when_private_key_available_then_key_is_stored(self, patch_push):
        event = Mock()
        private_key = "whatever"
        event.private_key = private_key
        container = self.harness.model.unit.get_container("magma-orc8r-bootstrapper")
        self.harness.set_can_connect(container=container, val=True)

        self.harness.charm._on_private_key_available(event=event)

        patch_push.assert_called_with(
            path="/var/opt/magma/certs/bootstrapper.key", source="whatever"
        )
