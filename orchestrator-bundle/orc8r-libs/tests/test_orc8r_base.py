# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, PropertyMock, patch

from ops import testing
from test_orc8r_base_charm.src.charm import (  # type: ignore[import]
    MagmaOrc8rDummyCharmWithoutRelation,
    MagmaOrc8rDummyCharmWithRelation,
)

testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    @patch(
        "test_orc8r_base_charm.src.charm.KubernetesServicePatch",
        lambda charm, ports, additional_labels: None,
    )
    def setUp(self):
        self.harness = testing.Harness(MagmaOrc8rDummyCharmWithoutRelation)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch("charms.magma_orc8r_libs.v0.orc8r_base.Orc8rBase.namespace", new_callable=PropertyMock)
    def test_given_pebble_ready_when_get_pebble_plan_then_plan_is_filled_with_orc8r_service_content(  # noqa: E501
        self, patch_namespace
    ):
        namespace = "whatever"
        patch_namespace.return_value = namespace
        expected_plan = {
            "services": {
                "magma-orc8r-dummy": {
                    "override": "replace",
                    "summary": "magma-orc8r-dummy",
                    "startup": "enabled",
                    "command": "/usr/bin/envdir "
                    "/var/opt/magma/envdir "
                    "/var/opt/magma/bin/dummy "
                    "-logtostderr=true "
                    "-v=0",
                    "environment": {
                        "SERVICE_HOSTNAME": "magma-orc8r-dummy",
                        "SERVICE_REGISTRY_MODE": "k8s",
                        "SERVICE_REGISTRY_NAMESPACE": namespace,
                    },
                }
            },
        }
        self.harness.container_pebble_ready("magma-orc8r-dummy")

        updated_plan = self.harness.get_container_pebble_plan("magma-orc8r-dummy").to_dict()
        self.assertEqual(expected_plan, updated_plan)


class TestCharmWithRelation(unittest.TestCase):
    @patch(
        "test_orc8r_base_charm.src.charm.KubernetesServicePatch",
        lambda charm, ports, additional_labels: None,
    )
    def setUp(self):
        self.harness = testing.Harness(MagmaOrc8rDummyCharmWithRelation)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch("ops.charm.PebbleReadyEvent.defer")
    def test_given_relation_is_not_created_when_pebble_ready_then_event_is_deferred(
        self, patch_defer
    ):
        event = Mock()

        self.harness.charm.on.magma_orc8r_dummy_pebble_ready.emit(event)

        patch_defer.assert_called()
