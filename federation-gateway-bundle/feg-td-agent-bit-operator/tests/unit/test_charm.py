# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import PropertyMock, call, patch

from ops import testing
from ops.model import ActiveStatus, WaitingStatus

from charm import FegTdAgentBitCharm

testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.container_name = "magma-feg-td-agent-bit"
        self.harness = testing.Harness(FegTdAgentBitCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch("charm.FegTdAgentBitCharm._fluent_bit_config_is_stored", new_callable=PropertyMock)
    @patch("ops.model.Container.exists")
    def test_given_can_connect_to_container_and_and_fluent_bit_config_file_is_not_stored_when_pebble_ready_then_status_is_waiting(
        self, patch_file_exists, patch_fluent_bit_config_is_stored
    ):
        patch_file_exists.return_value = True
        patch_fluent_bit_config_is_stored.return_value = False

        self.harness.charm.on.install.emit()
        self.harness.container_pebble_ready(container_name=self.container_name)

        self.assertEqual(
            self.harness.charm.unit.status,
            WaitingStatus("Waiting for fluent bit config to be available"),
        )

    @patch("ops.model.Container.exists")
    def test_given_can_connect_to_container_and_fluent_bit_config_file_is_stored_when_pebble_ready_then_status_is_active(  # noqa: E501
        self, patch_file_exists
    ):
        patch_file_exists.return_value = True

        self.harness.charm.on.install.emit()
        self.harness.container_pebble_ready(container_name=self.container_name)

        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    @patch("ops.model.Container.exists")
    def test_given_can_connect_to_container_and_fluent_bit_config_file_stored_when_pebble_ready_then_td_agent_bit_service_added_to_pebble_plan(  # noqa: E501
        self, patch_file_exists
    ):
        patch_file_exists.return_value = True

        self.harness.charm.on.install.emit()
        self.harness.container_pebble_ready(container_name=self.container_name)

        expected_plan = {
            "services": {
                "magma-feg-td-agent-bit": {
                    "override": "replace",
                    "summary": "magma-feg-td-agent-bit",
                    "command": "/opt/td-agent-bit/bin/td-agent-bit -c "
                    "'/var/opt/magma/tmp/td-agent-bit.conf'",
                    "startup": "enabled",
                }
            },
        }
        updated_plan = self.harness.get_container_pebble_plan("magma-feg-td-agent-bit").to_dict()

        self.assertEqual(expected_plan, updated_plan)

    @patch("ops.model.Container.exec")
    def test_given_can_connect_to_container_when_on_install_then_fluent_bit_config_file_is_created(
        self, patch_exec
    ):
        self.harness.container_pebble_ready(container_name=self.container_name)
        self.harness.charm.on.install.emit()

        patch_exec.assert_has_calls(
            calls=[call(command=["/usr/local/bin/generate_fluent_bit_config.py"])]
        )
