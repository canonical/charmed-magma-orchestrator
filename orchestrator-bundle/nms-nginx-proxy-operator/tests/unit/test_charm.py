# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, PropertyMock, patch

from ops import testing
from ops.model import BlockedStatus, WaitingStatus

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
            BlockedStatus(
                "Waiting for relation(s) to be created: magma-orc8r-certifier, magma-nms-magmalte"
            ),
        )

    def test_given_charm_when_pebble_ready_event_emitted_and_certifier_relation_is_missing_then_charm_goes_to_blocked_state(  # noqa: E501
        self,
    ):
        event = Mock()
        magmalte_relation_id = self.harness.add_relation("magma-nms-magmalte", "nms-magmalte")
        self.harness.add_relation_unit(magmalte_relation_id, "nms-magmalte/0")
        self.harness.charm.on.magma_nms_nginx_proxy_pebble_ready.emit(event)
        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for relation(s) to be created: magma-orc8r-certifier"),
        )

    def test_given_charm_when_pebble_ready_event_emitted_and_magmalte_relation_is_missing_then_charm_goes_to_blocked_state(  # noqa: E501
        self,
    ):
        self.harness.disable_hooks()
        event = Mock()
        certifier_relation_id = self.harness.add_relation(
            "magma-orc8r-certifier", "orc8r-certifier"
        )
        self.harness.add_relation_unit(certifier_relation_id, "orc8r-certifier/0")
        self.harness.enable_hooks()
        self.harness.charm.on.magma_nms_nginx_proxy_pebble_ready.emit(event)
        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for relation(s) to be created: magma-nms-magmalte"),
        )

    def test_given_relations_created_but_not_ready_when_pebble_ready_event_emitted_then_charm_goes_to_waiting_state(  # noqa: E501
        self,
    ):
        self.harness.disable_hooks()
        event = Mock()
        certifier_relation_id = self.harness.add_relation(
            "magma-orc8r-certifier", "orc8r-orchestrator"
        )
        self.harness.add_relation_unit(certifier_relation_id, "orc8r-orchestrator/0")
        magmalte_relation_id = self.harness.add_relation("magma-nms-magmalte", "nms-magmalte")
        self.harness.add_relation_unit(magmalte_relation_id, "nms-magmalte/0")
        self.harness.enable_hooks()
        self.harness.charm.on.magma_nms_nginx_proxy_pebble_ready.emit(event)
        self.assertEqual(
            self.harness.charm.unit.status,
            WaitingStatus(
                "Waiting for relation(s) to be ready: magma-orc8r-certifier, magma-nms-magmalte"
            ),
        )

    def test_given_relations_created_but_magma_nms_magmalte_not_ready_when_pebble_ready_event_emitted_then_charm_goes_to_waiting_state(  # noqa: E501
        self,
    ):
        self.harness.disable_hooks()
        event = Mock()
        certifier_relation_id = self.harness.add_relation(
            "magma-orc8r-certifier", "orc8r-certifier"
        )
        self.harness.add_relation_unit(certifier_relation_id, "orc8r-certifier/0")
        magmalte_relation_id = self.harness.add_relation("magma-nms-magmalte", "nms-magmalte")
        self.harness.add_relation_unit(magmalte_relation_id, "nms-magmalte/0")
        self.harness.update_relation_data(
            certifier_relation_id, "orc8r-certifier/0", {"active": "True"}
        )
        self.harness.enable_hooks()
        self.harness.charm.on.magma_nms_nginx_proxy_pebble_ready.emit(event)
        self.assertEqual(
            self.harness.charm.unit.status,
            WaitingStatus("Waiting for relation(s) to be ready: magma-nms-magmalte"),
        )

    def test_given_relations_created_but_magma_orc8r_certifier_not_ready_when_pebble_ready_event_emitted_then_charm_goes_to_waiting_state(  # noqa: E501
        self,
    ):
        self.harness.disable_hooks()
        event = Mock()
        certifier_relation_id = self.harness.add_relation(
            "magma-orc8r-certifier", "orc8r-certifier"
        )
        self.harness.add_relation_unit(certifier_relation_id, "orc8r-certifier/0")
        magmalte_relation_id = self.harness.add_relation("magma-nms-magmalte", "nms-magmalte")
        self.harness.add_relation_unit(magmalte_relation_id, "nms-magmalte/0")
        self.harness.update_relation_data(
            magmalte_relation_id, "nms-magmalte/0", {"active": "True"}
        )
        self.harness.enable_hooks()
        self.harness.charm.on.magma_nms_nginx_proxy_pebble_ready.emit(event)
        self.assertEqual(
            self.harness.charm.unit.status,
            WaitingStatus("Waiting for relation(s) to be ready: magma-orc8r-certifier"),
        )

    @patch("charm.MagmaNmsNginxProxyCharm._nms_certs_mounted", PropertyMock(return_value=False))
    def test_given_relations_created_and_ready_but_nms_certs_not_mounted_when_pebble_ready_event_emitted_then_charm_goes_to_waiting_state(  # noqa: E501
        self,
    ):
        self.harness.disable_hooks()
        event = Mock()
        certifier_relation_id = self.harness.add_relation(
            "magma-orc8r-certifier", "orc8r-certifier"
        )
        self.harness.add_relation_unit(certifier_relation_id, "orc8r-certifier/0")
        magmalte_relation_id = self.harness.add_relation("magma-nms-magmalte", "nms-magmalte")
        self.harness.add_relation_unit(magmalte_relation_id, "nms-magmalte/0")
        self.harness.update_relation_data(
            certifier_relation_id, "orc8r-certifier/0", {"active": "True"}
        )
        self.harness.update_relation_data(
            magmalte_relation_id, "nms-magmalte/0", {"active": "True"}
        )
        self.harness.enable_hooks()
        self.harness.charm.on.magma_nms_nginx_proxy_pebble_ready.emit(event)
        self.assertEqual(
            self.harness.charm.unit.status,
            WaitingStatus("Waiting for NMS certificates to be mounted"),
        )

    @patch("charm.MagmaNmsNginxProxyCharm._nms_certs_mounted", PropertyMock(return_value=True))
    @patch(
        "charm.MagmaNmsNginxProxyCharm._nginx_proxy_etc_configmap_created",
        PropertyMock(return_value=False),
    )
    def test_given_relations_created_and_ready_nms_certs_mounted_but_nginx_proxy_configmap_not_created_when_pebble_ready_event_emitted_then_charm_goes_to_waiting_state(  # noqa: E501
        self,
    ):
        self.harness.disable_hooks()
        event = Mock()
        certifier_relation_id = self.harness.add_relation(
            "magma-orc8r-certifier", "orc8r-certifier"
        )
        self.harness.add_relation_unit(certifier_relation_id, "orc8r-certifier/0")
        magmalte_relation_id = self.harness.add_relation("magma-nms-magmalte", "nms-magmalte")
        self.harness.add_relation_unit(magmalte_relation_id, "nms-magmalte/0")
        self.harness.update_relation_data(
            certifier_relation_id, "orc8r-certifier/0", {"active": "True"}
        )
        self.harness.update_relation_data(
            magmalte_relation_id, "nms-magmalte/0", {"active": "True"}
        )
        self.harness.enable_hooks()
        self.harness.charm.on.magma_nms_nginx_proxy_pebble_ready.emit(event)
        self.assertEqual(
            self.harness.charm.unit.status,
            WaitingStatus("Waiting for required Kubernetes resources to be created"),
        )

    @patch("charm.MagmaNmsNginxProxyCharm._namespace", new_callable=PropertyMock)
    @patch("charm.MagmaNmsNginxProxyCharm._relations_ready", PropertyMock(return_value=True))
    @patch("charm.MagmaNmsNginxProxyCharm._relations_created", PropertyMock(return_value=True))
    @patch("charm.MagmaNmsNginxProxyCharm._nms_certs_mounted", PropertyMock(return_value=True))
    @patch(
        "charm.MagmaNmsNginxProxyCharm._nginx_proxy_etc_configmap_created",
        PropertyMock(return_value=True),
    )
    def test_given_required_relations_are_present_when_pebble_ready_event_emitted_then_pebble_is_configured_with_correct_plan(  # noqa: E501
        self, patch_namespace
    ):
        patch_namespace.return_value = "whatever"
        expected_plan = {
            "services": {
                "magma-nms-nginx-proxy": {
                    "override": "replace",
                    "startup": "enabled",
                    "command": "nginx",
                }
            }
        }
        self.harness.set_can_connect("magma-nms-nginx-proxy", True)
        self.harness.container_pebble_ready("magma-nms-nginx-proxy")
        updated_plan = self.harness.get_container_pebble_plan("magma-nms-nginx-proxy").to_dict()
        self.assertEqual(expected_plan, updated_plan)

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
