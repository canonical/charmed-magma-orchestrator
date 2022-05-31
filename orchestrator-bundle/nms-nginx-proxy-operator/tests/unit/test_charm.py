# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, patch

from ops import testing
from ops.model import BlockedStatus

from charm import MagmaNmsNginxProxyCharm

testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports, service_type, service_name, additional_labels: None,
    )
    def setUp(self):
        self.harness = testing.Harness(MagmaNmsNginxProxyCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_given_charm_when_pebble_ready_event_emitted_and_no_relations_established_then_charm_goes_to_blocked_state(  # noqa: E501
        self,
    ):
        event = Mock()
        self.harness.charm.on.magma_nms_nginx_proxy_pebble_ready.emit(event)
        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for relations: magma-orc8r-certifier, magmalte"),
        )

    def test_given_charm_when_pebble_ready_event_emitted_and_certifier_relation_is_missing_then_charm_goes_to_blocked_state(  # noqa: E501
        self,
    ):
        event = Mock()
        magmalte_relation_id = self.harness.add_relation("magmalte", "nms-magmalte")
        self.harness.add_relation_unit(magmalte_relation_id, "nms-magmalte/0")
        self.harness.charm.on.magma_nms_nginx_proxy_pebble_ready.emit(event)
        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for relations: magma-orc8r-certifier"),
        )

    def test_given_charm_when_pebble_ready_event_emitted_and_magmalte_relation_is_missing_then_charm_goes_to_blocked_state(  # noqa: E501
        self,
    ):
        self.harness.disable_hooks()
        event = Mock()
        orc8r_relation_id = self.harness.add_relation(
            "magma-orc8r-certifier", "orc8r-orchestrator"
        )
        self.harness.add_relation_unit(orc8r_relation_id, "orc8r-orchestrator/0")
        self.harness.enable_hooks()
        self.harness.charm.on.magma_nms_nginx_proxy_pebble_ready.emit(event)
        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for relations: magmalte"),
        )

    def test_given_charm_when_pebble_ready_event_emitted_and_required_relations_are_present_then_configure_pebble_action_is_called(  # noqa: E501
        self,
    ):
        self.harness.disable_hooks()
        event = Mock()
        orc8r_relation_id = self.harness.add_relation(
            "magma-orc8r-certifier", "orc8r-orchestrator"
        )
        self.harness.add_relation_unit(orc8r_relation_id, "orc8r-orchestrator/0")
        magmalte_relation_id = self.harness.add_relation("magmalte", "nms-magmalte")
        self.harness.add_relation_unit(magmalte_relation_id, "nms-magmalte/0")
        self.harness.enable_hooks()
        with patch.object(MagmaNmsNginxProxyCharm, "_configure_pebble") as mock:
            self.harness.charm.on.magma_nms_nginx_proxy_pebble_ready.emit(event)
        mock.assert_called_once()

    def test_given_charm_when_certifier_relation_added_then_configure_nginx_action_called(self):
        event = Mock()
        with patch.object(MagmaNmsNginxProxyCharm, "_configure_nginx", event) as mock:
            relation_id = self.harness.add_relation("magma-orc8r-certifier", "orc8r-certifier")
            self.harness.add_relation_unit(relation_id, "orc8r-certifier/0")
            self.harness.update_relation_data(relation_id, "orc8r-certifier/0", {"key": "value"})
        mock.assert_called_once()

    def test_given_charm_when_remove_event_emitted_then_on_remove_action_called(self):
        with patch.object(MagmaNmsNginxProxyCharm, "_on_remove") as mock:
            self.harness.charm.on.remove.emit()
        mock.assert_called_once()
