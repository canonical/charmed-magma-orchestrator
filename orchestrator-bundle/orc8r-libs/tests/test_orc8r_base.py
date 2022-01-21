# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch

from ops.testing import Harness
from test_orc8r_base_charm.src.charm import MagmaOrc8rHACharm  # type: ignore[import]


class TestCharm(unittest.TestCase):
    @patch("test_orc8r_base_charm.src.charm.KubernetesServicePatch", lambda x, y: None)
    def setUp(self):
        self.harness = Harness(MagmaOrc8rHACharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_given_initial_status_when_get_pebble_plan_then_content_is_empty(self):
        initial_plan = self.harness.get_container_pebble_plan("magma-orc8r-ha")
        self.assertEqual(initial_plan.to_yaml(), "{}\n")

    def test_given_pebble_ready_when_get_pebble_plan_then_plan_is_filled_with_orc8r_service_content(  # noqa: E501
        self,
    ):
        expected_plan = {
            "services": {
                "magma-orc8r-ha": {
                    "override": "replace",
                    "summary": "magma-orc8r-ha",
                    "startup": "enabled",
                    "command": "/usr/bin/envdir "
                    "/var/opt/magma/envdir "
                    "/var/opt/magma/bin/ha "
                    "-logtostderr=true "
                    "-v=0",
                    "environment": {
                        "SERVICE_HOSTNAME": "magma-orc8r-ha",
                    },
                }
            },
        }
        container = self.harness.model.unit.get_container("magma-orc8r-ha")
        self.harness.charm.on.magma_orc8r_ha_pebble_ready.emit(container)
        updated_plan = self.harness.get_container_pebble_plan("magma-orc8r-ha").to_dict()
        self.assertEqual(expected_plan, updated_plan)
