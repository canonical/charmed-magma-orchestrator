# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch

from ops.testing import Harness

from charm import MagmaOrc8rServiceRegistry


class TestCharm(unittest.TestCase):
    @patch("charm.KubernetesServicePatch", lambda x, y: None)
    def setUp(self):
        self.harness = Harness(MagmaOrc8rServiceRegistry)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_given_initial_status_when_get_pebble_plan_then_content_is_empty(self):
        initial_plan = self.harness.get_container_pebble_plan("magma-orc8r-service-registry")
        self.assertEqual(initial_plan.to_yaml(), "{}\n")

    @patch("charm.MagmaOrc8rServiceRegistry.model")
    def test_given_pebble_ready_when_get_pebble_plan_then_plan_is_filled_with_orc8r_service_content(  # noqa: E501
        self, mock_model_name
    ):
        namespace = "whatever namespace"
        mock_model_name.name = namespace
        expected_plan = {
            "services": {
                "magma-orc8r-service-registry": {
                    "override": "replace",
                    "summary": "magma-orc8r-service-registry",
                    "startup": "enabled",
                    "command": "/usr/bin/envdir "
                    "/var/opt/magma/envdir "
                    "/var/opt/magma/bin/service_registry "
                    "-logtostderr=true "
                    "-v=0",
                    "environment": {
                        "SERVICE_REGISTRY_MODE": "k8s",
                        "SERVICE_REGISTRY_NAMESPACE": namespace,
                    },
                }
            },
        }
        container = self.harness.model.unit.get_container("magma-orc8r-service-registry")
        self.harness.charm.on.magma_orc8r_service_registry_pebble_ready.emit(container)
        updated_plan = self.harness.get_container_pebble_plan(
            "magma-orc8r-service-registry"
        ).to_dict()
        self.assertEqual(expected_plan, updated_plan)
