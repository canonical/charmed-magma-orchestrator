# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, PropertyMock, patch

from ops import testing
from ops.model import BlockedStatus

from charm import MagmaOrc8rBootstrapperCharm

testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    @patch("charm.KubernetesServicePatch", lambda charm, ports, additional_labels: None)
    def setUp(self):
        self.harness = testing.Harness(MagmaOrc8rBootstrapperCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.maxDiff = None

    def test_given_charm_when_pebble_ready_event_emitted_and_no_relations_established_then_charm_goes_to_blocked_state(  # noqa: E501
        self,
    ):
        event = Mock()
        self.harness.charm.on.magma_orc8r_bootstrapper_pebble_ready.emit(event)
        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for magma-orc8r-certifier relation to be created"),
        )

    @patch("charm.MagmaOrc8rBootstrapperCharm._namespace", new_callable=PropertyMock)
    @patch(
        "charm.MagmaOrc8rBootstrapperCharm._orc8r_certs_mounted", PropertyMock(return_value=True)
    )
    @patch(
        "charm.MagmaOrc8rBootstrapperCharm._certifier_relation_ready",
        PropertyMock(return_value=True),
    )
    @patch(
        "charm.MagmaOrc8rBootstrapperCharm._certifier_relation_created",
        PropertyMock(return_value=True),
    )
    def test_given_ready_when_get_plan_then_plan_is_filled_with_magma_orc8r_bootstrapper_service_content(  # noqa: E501
        self, patch_namespace
    ):
        namespace = "whatever"
        patch_namespace.return_value = namespace
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
                        "SERVICE_REGISTRY_NAMESPACE": namespace,
                    },
                },
            },
        }
        self.harness.container_pebble_ready("magma-orc8r-bootstrapper")

        updated_plan = self.harness.get_container_pebble_plan("magma-orc8r-bootstrapper").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    @patch("charm.MagmaOrc8rBootstrapperCharm._mount_orc8r_certs")
    @patch(
        "charm.MagmaOrc8rBootstrapperCharm._orc8r_certs_mounted", PropertyMock(return_value=False)
    )
    def test_given_charm_with_certifier_relation_active_when_certs_are_not_mounted_then_mount_orc8r_certs(  # noqa: E501
        self, mock_on_certifier_relation_changed
    ):
        relation_id = self.harness.add_relation("magma-orc8r-certifier", "orc8r-certifier")
        self.harness.add_relation_unit(relation_id, "orc8r-certifier/0")
        self.harness.update_relation_data(relation_id, "orc8r-certifier/0", {"active": "True"})

        mock_on_certifier_relation_changed.assert_called_once()

    @patch("charm.MagmaOrc8rBootstrapperCharm._mount_orc8r_certs")
    @patch(
        "charm.MagmaOrc8rBootstrapperCharm._orc8r_certs_mounted", PropertyMock(return_value=True)
    )
    def test_given_charm_with_certifier_relation_active_when_certs_are_mounted_then_dont_mount_orc8r_certs(  # noqa: E501
        self, mock_on_certifier_relation_changed
    ):
        relation_id = self.harness.add_relation("magma-orc8r-certifier", "orc8r-certifier")
        self.harness.add_relation_unit(relation_id, "orc8r-certifier/0")
        self.harness.update_relation_data(relation_id, "orc8r-certifier/0", {"active": "True"})

        mock_on_certifier_relation_changed.assert_not_called()

    @patch("charm.MagmaOrc8rBootstrapperCharm._namespace", PropertyMock(return_value="qwerty"))
    @patch(
        "charm.MagmaOrc8rBootstrapperCharm._certifier_relation_ready",
        PropertyMock(return_value=True),
    )
    @patch(
        "charm.MagmaOrc8rBootstrapperCharm._certifier_relation_created",
        PropertyMock(return_value=True),
    )
    @patch(
        "charm.MagmaOrc8rBootstrapperCharm._orc8r_certs_mounted", PropertyMock(return_value=True)
    )
    def test_given_magma_orc8r_bootstrapper_service_running_when_magma_orc8r_bootstrapper_relation_joined_event_emitted_then_active_key_in_relation_data_is_set_to_true(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect("magma-orc8r-bootstrapper", True)
        container = self.harness.model.unit.get_container("magma-orc8r-bootstrapper")
        self.harness.charm.on.magma_orc8r_bootstrapper_pebble_ready.emit(container)
        self.harness.set_leader(True)
        relation_id = self.harness.add_relation(
            "magma-orc8r-bootstrapper", "orc8r-bootstrapper"
        )
        self.harness.add_relation_unit(relation_id, "magma-orc8r-bootstrapper/0")

        self.assertEqual(
            self.harness.get_relation_data(relation_id, "magma-orc8r-bootstrapper/0"),
            {"active": "True"},
        )

    @patch("charm.MagmaOrc8rBootstrapperCharm._namespace", PropertyMock(return_value="qwerty"))
    @patch(
        "charm.MagmaOrc8rBootstrapperCharm._certifier_relation_ready",
        PropertyMock(return_value=True),
    )
    @patch(
        "charm.MagmaOrc8rBootstrapperCharm._certifier_relation_created",
        PropertyMock(return_value=True),
    )
    @patch(
        "charm.MagmaOrc8rBootstrapperCharm._orc8r_certs_mounted", PropertyMock(return_value=True)
    )
    def test_given_magma_orc8r_bootstrapper_service_not_running_when_magma_orc8r_bootstrapper_relation_joined_event_emitted_then_active_key_in_relation_data_is_set_to_false(  # noqa: E501
        self,
    ):
        self.harness.set_leader(True)
        relation_id = self.harness.add_relation(
            "magma-orc8r-bootstrapper", "orc8r-bootstrapper"
        )
        self.harness.add_relation_unit(relation_id, "magma-orc8r-bootstrapper/0")

        self.assertEqual(
            self.harness.get_relation_data(relation_id, "magma-orc8r-bootstrapper/0"),
            {"active": "False"},
        )