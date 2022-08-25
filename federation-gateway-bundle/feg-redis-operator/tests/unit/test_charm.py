# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import call, patch

from ops import testing
from ops.model import ActiveStatus, WaitingStatus

from charm import FegRedisCharm

testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):

    BASE_SERVICE_CONFIG_PATH = "/var/opt/magma/tmp"

    def setUp(self):
        self.container_name = "magma-feg-redis"
        self.harness = testing.Harness(FegRedisCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch("ops.model.Container.exec")
    def test_given_can_connect_to_container_when_on_install_then_config_file_is_created(
        self, patch_exec
    ):
        self.harness.container_pebble_ready(container_name=self.container_name)
        self.harness.charm.on.install.emit()

        patch_exec.assert_has_calls(
            calls=[
                call(
                    command=[
                        "/usr/local/bin/generate_service_config.py",
                        "--service=redis",
                        "--template=redis",
                    ]
                )
            ]
        )

    @patch("ops.model.Container.exists")
    def test_given_can_connect_to_container_and_service_config_file_is_not_stored_when_pebble_ready_then_status_is_waiting(
        self, patch_exists
    ):
        patch_exists.return_value = False

        self.harness.container_pebble_ready(container_name=self.container_name)

        self.assertEqual(
            self.harness.model.unit.status,
            WaitingStatus("Waiting for service config to be available"),
        )

    @patch("ops.model.Container.exists")
    def test_given_can_connect_to_container_and_service_config_file_is_stored_when_pebble_ready_then_status_is_active(
        self, patch_exists
    ):
        patch_exists.return_value = True

        self.harness.container_pebble_ready(container_name=self.container_name)

        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    @patch("ops.model.Container.exists")
    def test_given_can_connect_to_container_and_service_config_file_is_stored_when_pebble_ready_then_redis_service_added_to_pebble_plan(  # noqa: E501
        self, patch_exists
    ):
        patch_exists.return_value = True

        self.harness.container_pebble_ready(container_name=self.container_name)

        expected_plan = {
            "services": {
                "magma-feg-redis": {
                    "override": "replace",
                    "summary": "magma-feg-redis",
                    "command": f'/bin/bash -c "/usr/bin/redis-server {self.BASE_SERVICE_CONFIG_PATH}/redis.conf --daemonize no && /usr/bin/redis-cli shutdown"',
                    "startup": "enabled",
                }
            },
        }
        updated_plan = self.harness.get_container_pebble_plan("magma-feg-redis").to_dict()

        self.assertEqual(expected_plan, updated_plan)
