# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, PropertyMock, patch

from ops.model import BlockedStatus
from ops.testing import Harness

from charm import MagmaOrc8rBootstrapperCharm


class TestCharm(unittest.TestCase):
    @patch("charm.KubernetesServicePatch", lambda charm, ports, additional_labels: None)
    def setUp(self):
        self.harness = Harness(MagmaOrc8rBootstrapperCharm)
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
            BlockedStatus("Waiting for orc8r-certifier relation..."),
        )

    def test_given_initial_status_when_get_pebble_plan_then_content_is_empty(self):
        initial_plan = self.harness.get_container_pebble_plan("magma-orc8r-bootstrapper")
        self.assertEqual(initial_plan.to_yaml(), "{}\n")

    @patch("charm.MagmaOrc8rBootstrapperCharm._namespace", new_callable=PropertyMock)
    @patch("charm.MagmaOrc8rBootstrapperCharm._certifier_relation_ready")
    def test_given_ready_when_get_plan_then_plan_is_filled_with_magma_orc8r_bootstrapper_service_content(  # noqa: E501
        self, certifier_relation_ready, patch_namespace
    ):
        namespace = "whatever"
        certifier_relation_ready.return_value = True
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
        container = self.harness.model.unit.get_container("magma-orc8r-bootstrapper")
        self.harness.charm.on.magma_orc8r_bootstrapper_pebble_ready.emit(container)
        updated_plan = self.harness.get_container_pebble_plan("magma-orc8r-bootstrapper").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    def test_given_charm_when_certifier_relation_added_then_on_certifier_relation_joined_action_called(  # noqa: E501
        self,
    ):
        event = Mock()
        with patch.object(
            MagmaOrc8rBootstrapperCharm, "_on_certifier_relation_joined", event
        ) as mock:
            relation_id = self.harness.add_relation("certifier", "orc8r-certifier")
            self.harness.add_relation_unit(relation_id, "orc8r-certifier/0")
            self.harness.update_relation_data(relation_id, "orc8r-certifier/0", {})
        mock.assert_called_once()
