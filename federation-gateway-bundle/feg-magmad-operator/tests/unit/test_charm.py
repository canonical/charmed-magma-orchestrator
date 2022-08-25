# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, call, patch

from ops import testing
from ops.model import ActiveStatus

from charm import FegMagmadCharm

testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.container_name = "magma-feg-magmad"
        self.harness = testing.Harness(FegMagmadCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch("ops.model.Container.exec")
    def test_given_can_connect_to_container_and_active_status_when_show_gateway_info_action_is_triggered_then_show_gateway_info_command_is_executed(  # noqa: E501
        self,
        patch_exec,
    ):
        mock_event = Mock()
        mock_return_value = Mock()
        mock_return_value.wait_output.return_value = ("stdout", "stderr")
        patch_exec.return_value = mock_return_value

        self.harness.container_pebble_ready(container_name=self.container_name)
        self.harness.charm._on_show_gateway_info_action(mock_event)

        patch_exec.assert_has_calls(
            calls=[
                call(command=["/usr/local/bin/show_gateway_info.py"]),
                call().wait_output(),
            ]
        )
        mock_event.set_results.assert_called_once_with({"result": "stdout"})

    def test_given_can_connect_to_container_when_pebble_ready_then_status_is_active(self):

        self.harness.container_pebble_ready(container_name=self.container_name)

        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    def test_given_can_connect_to_container_when_pebble_ready_then_magmad_service_added_to_pebble_plan(  # noqa: E501
        self,
    ):

        self.harness.container_pebble_ready(container_name=self.container_name)

        expected_plan = {
            "services": {
                "magma-feg-magmad": {
                    "override": "replace",
                    "summary": "magma-feg-magmad",
                    "command": "python3.8 -m magma.magmad.main",
                    "startup": "enabled",
                }
            },
        }
        updated_plan = self.harness.get_container_pebble_plan("magma-feg-magmad").to_dict()

        self.assertEqual(expected_plan, updated_plan)
