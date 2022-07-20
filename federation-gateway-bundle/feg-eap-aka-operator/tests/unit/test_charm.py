# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest

from ops import testing
from ops.model import ActiveStatus

from charm import FegEapAkaCharm

testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.container_name = "magma-feg-eap-aka"
        self.harness = testing.Harness(FegEapAkaCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_given_can_connect_to_container_when_pebble_ready_then_status_is_active(self):

        self.harness.container_pebble_ready(container_name=self.container_name)

        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    def test_given_can_connect_to_container_when_pebble_ready_then_eap_aka_service_added_to_pebble_plan(  # noqa: E501
        self,
    ):

        self.harness.container_pebble_ready(container_name=self.container_name)

        expected_plan = {
            "services": {
                "magma-feg-eap-aka": {
                    "override": "replace",
                    "summary": "magma-feg-eap-aka",
                    "command": "envdir "
                    "/var/opt/magma/envdir "
                    "/var/opt/magma/bin/eap_aka "
                    "-logtostderr=true "
                    "-v=0",
                    "startup": "enabled",
                }
            },
        }
        updated_plan = self.harness.get_container_pebble_plan("magma-feg-eap-aka").to_dict()

        self.assertEqual(expected_plan, updated_plan)
