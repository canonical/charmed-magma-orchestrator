# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest

from ops import testing
from ops.model import ActiveStatus

from charm import FegS6aProxyCharm

testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.container_name = "magma-feg-s6a-proxy"
        self.harness = testing.Harness(FegS6aProxyCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_given_can_connect_to_container_when_pebble_ready_then_status_is_active(self):

        self.harness.container_pebble_ready(container_name=self.container_name)

        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    def test_given_can_connect_to_container_when_pebble_ready_then_s6a_proxy_service_added_to_pebble_plan(  # noqa: E501
        self,
    ):

        self.harness.container_pebble_ready(container_name=self.container_name)

        expected_plan = {
            "services": {
                "magma-feg-s6a-proxy": {
                    "override": "replace",
                    "summary": "magma-feg-s6a-proxy",
                    "command": "envdir "
                    "/var/opt/magma/envdir "
                    "/var/opt/magma/bin/s6a_proxy "
                    "-logtostderr=true "
                    "-v=0",
                    "startup": "enabled",
                }
            },
        }
        updated_plan = self.harness.get_container_pebble_plan("magma-feg-s6a-proxy").to_dict()

        self.assertEqual(expected_plan, updated_plan)
