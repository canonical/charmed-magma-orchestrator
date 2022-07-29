# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest

from ops import testing
from ops.model import ActiveStatus

from charm import FegTdAgentBitCharm

testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.container_name = "magma-feg-td-agent-bit"
        self.harness = testing.Harness(FegTdAgentBitCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_given_can_connect_to_container_when_pebble_ready_then_status_is_active(self):

        self.harness.container_pebble_ready(container_name=self.container_name)

        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    def test_given_can_connect_to_container_when_pebble_ready_then_td_agent_bit_service_added_to_pebble_plan(  # noqa: E501
        self,
    ):

        self.harness.container_pebble_ready(container_name=self.container_name)

        expected_plan = {
            "services": {
                "magma-feg-td-agent-bit": {
                    "override": "replace",
                    "summary": "magma-feg-td-agent-bit",
                    "command": "/bin/bash -c "
                    "'/usr/local/bin/generate_fluent_bit_config.py && "
                    "/opt/td-agent-bit/bin/td-agent-bit -c /var/opt/magma/tmp/td-agent-bit.conf'",
                    "startup": "enabled",
                }
            },
        }
        updated_plan = self.harness.get_container_pebble_plan("magma-feg-td-agent-bit").to_dict()

        self.assertEqual(expected_plan, updated_plan)
