# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest

from ops import testing
from ops.model import ActiveStatus

from charm import FegRedisCharm

testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.container_name = "magma-feg-redis"
        self.harness = testing.Harness(FegRedisCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_given_can_connect_to_container_when_pebble_ready_then_status_is_active(self):

        self.harness.container_pebble_ready(container_name=self.container_name)

        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    def test_given_can_connect_to_container_when_pebble_ready_then_redis_service_added_to_pebble_plan(  # noqa: E501
        self,
    ):

        self.harness.container_pebble_ready(container_name=self.container_name)

        expected_plan = {
            "services": {
                "magma-feg-redis": {
                    "override": "replace",
                    "summary": "magma-feg-redis",
                    "command": '/bin/bash -c "/usr/local/bin/generate_service_config.py '
                    "--service=redis --template=redis "
                    "&& /usr/bin/redis-server /var/opt/magma/tmp/redis.conf --daemonize no "
                    '&& /usr/bin/redis-cli shutdown"',
                    "startup": "enabled",
                }
            },
        }
        updated_plan = self.harness.get_container_pebble_plan("magma-feg-redis").to_dict()

        self.assertEqual(expected_plan, updated_plan)
