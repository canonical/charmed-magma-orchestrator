# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, PropertyMock, patch

from ops.testing import Harness

from charm import MagmaOrc8rOrchestratorCharm


class TestCharm(unittest.TestCase):
    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports, additional_labels, additional_annotations: None,
    )
    def setUp(self):
        self.harness = Harness(MagmaOrc8rOrchestratorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_given_initial_status_when_get_pebble_plan_then_content_is_empty(self):
        initial_plan = self.harness.get_container_pebble_plan("magma-orc8r-orchestrator")
        self.assertEqual(initial_plan.to_yaml(), "{}\n")

    @patch("charm.MagmaOrc8rOrchestratorCharm._namespace", new_callable=PropertyMock)
    @patch("charm.MagmaOrc8rOrchestratorCharm._relations_ready")
    def test_given_ready_when_get_plan_then_plan_is_filled_with_magma_nms_magmalte_service_content(
        self, relations_ready, patch_namespace
    ):
        event = Mock()
        namespace = "whatever"
        relations_ready.return_value = True
        patch_namespace.return_value = namespace
        expected_plan = {
            "services": {
                "magma-orc8r-orchestrator": {
                    "startup": "enabled",
                    "override": "replace",
                    "command": "/usr/bin/envdir "
                    "/var/opt/magma/envdir "
                    "/var/opt/magma/bin/orchestrator "
                    "-run_echo_server=true "
                    "-logtostderr=true -v=0",
                    "environment": {
                        "SERVICE_HOSTNAME": "magma-orc8r-orchestrator",
                        "SERVICE_REGISTRY_MODE": "k8s",
                        "SERVICE_REGISTRY_NAMESPACE": namespace,
                    },
                },
            },
        }
        self.harness.charm.on.magma_orc8r_orchestrator_pebble_ready.emit(event)
        updated_plan = self.harness.get_container_pebble_plan("magma-orc8r-orchestrator").to_dict()
        self.assertEqual(expected_plan, updated_plan)
