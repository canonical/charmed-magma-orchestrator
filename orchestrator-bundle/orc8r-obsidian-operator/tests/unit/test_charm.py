# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch

from ops.testing import Harness

from charm import MagmaOrc8rObsidianCharm


class TestCharm(unittest.TestCase):
    @patch("charm.KubernetesServicePatch", lambda x, y: None)
    def setUp(self):
        self.harness = Harness(MagmaOrc8rObsidianCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_given_initial_status_when_get_pebble_plan_then_content_is_empty(self):
        initial_plan = self.harness.get_container_pebble_plan("magma-orc8r-obsidian")
        self.assertEqual(initial_plan.to_yaml(), "{}\n")

    def test_given_pebble_ready_when_get_pebble_plan_then_plan_is_filled_with_orc8r_service_content(  # noqa: E501
        self,
    ):
        expected_plan = {
            "services": {
                "magma-orc8r-obsidian": {
                    "override": "replace",
                    "summary": "magma-orc8r-obsidian",
                    "startup": "enabled",
                    "command": "/usr/bin/envdir "
                    "/var/opt/magma/envdir "
                    "/var/opt/magma/bin/obsidian "
                    "-logtostderr=true "
                    "-v=0",
                }
            },
        }
        container = self.harness.model.unit.get_container("magma-orc8r-obsidian")
        self.harness.charm.on.magma_orc8r_obsidian_pebble_ready.emit(container)
        updated_plan = self.harness.get_container_pebble_plan("magma-orc8r-obsidian").to_dict()
        self.assertEqual(expected_plan, updated_plan)
