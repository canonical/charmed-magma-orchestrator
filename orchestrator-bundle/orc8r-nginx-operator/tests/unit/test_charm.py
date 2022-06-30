# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, PropertyMock, patch

from ops import testing
from ops.model import BlockedStatus

from charm import MagmaOrc8rNginxCharm

testing.SIMULATE_CAN_CONNECT = True

"""
class MockExec:
    def exec(self, *args, **kwargs):
        pass

    def wait_output(self, *args, **kwargs):
        return("test output",any)
"""


class TestCharm(unittest.TestCase):
    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports, service_type, service_name, additional_labels, additional_selectors: None,  # noqa: E501
    )
    def setUp(self):
        self.harness = testing.Harness(MagmaOrc8rNginxCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_given_charm_when_pebble_ready_event_emitted_and_no_relations_established_then_charm_goes_to_blocked_state(  # noqa: E501
        self,
    ):
        event = Mock()
        self.harness.charm.on.magma_orc8r_nginx_pebble_ready.emit(event)
        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for relations: bootstrapper, certifier, obsidian"),
        )

    def test_given_charm_when_pebble_ready_event_emitted_and_certifier_relation_is_established_but_bootstrapper_and_obsidian_relations_are_missing_then_charm_goes_to_blocked_state(  # noqa: E501
        self,
    ):
        event = Mock()
        relation_id = self.harness.add_relation("certifier", "magma-orc8r-certifier")
        self.harness.add_relation_unit(relation_id, "magma-orc8r-certifier/0")
        self.harness.charm.on.magma_orc8r_nginx_pebble_ready.emit(event)
        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for relations: bootstrapper, obsidian"),
        )

    def test_given_charm_when_pebble_ready_event_emitted_and_bootstrapper_relation_is_established_but_certifier_and_obsidian_relations_are_missing_then_charm_goes_to_blocked_state(  # noqa: E501
        self,
    ):
        event = Mock()
        relation_id = self.harness.add_relation("bootstrapper", "magma-orc8r-bootstrapper")
        self.harness.add_relation_unit(relation_id, "magma-orc8r-bootstrapper/0")
        self.harness.charm.on.magma_orc8r_nginx_pebble_ready.emit(event)
        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for relations: certifier, obsidian"),
        )

    def test_given_charm_when_pebble_ready_event_emitted_and_all_relations_established_then_create_additional_orc8r_nginx_services_is_called(  # noqa: E501
        self,
    ):
        event = Mock()
        with patch.object(
            MagmaOrc8rNginxCharm,
            "_create_additional_orc8r_nginx_services",
        ) as mock:
            relation_id = self.harness.add_relation("bootstrapper", "magma-orc8r-bootstrapper")
            self.harness.add_relation_unit(relation_id, "magma-orc8r-bootstrapper/0")
            relation_id = self.harness.add_relation("certifier", "magma-orc8r-certifier")
            self.harness.add_relation_unit(relation_id, "magma-orc8r-certifier/0")
            relation_id = self.harness.add_relation("obsidian", "magma-orc8r-obsidian")
            self.harness.add_relation_unit(relation_id, "magma-orc8r-obsidian/0")
            with patch(
                "charm.MagmaOrc8rNginxCharm._get_domain_name", new_callable=PropertyMock
            ) as domain_name, patch(
                "charm.MagmaOrc8rNginxCharm._configure_pebble_layer", event
            ) as configure_pebble_layer:
                domain_name.return_value = "test.domain.com"
                configure_pebble_layer.return_value = Mock()
                self.harness.charm.on.magma_orc8r_nginx_pebble_ready.emit(event)
        mock.assert_called_once()

    def test_given_charm_when_pebble_ready_event_emitted_and_all_relations_established_then_configure_pebble_layer_is_called(  # noqa: E501
        self,
    ):
        event = Mock()
        with patch.object(MagmaOrc8rNginxCharm, "_configure_pebble_layer", event) as mock:
            relation_id = self.harness.add_relation("bootstrapper", "magma-orc8r-bootstrapper")
            self.harness.add_relation_unit(relation_id, "magma-orc8r-bootstrapper/0")
            relation_id = self.harness.add_relation("certifier", "magma-orc8r-certifier")
            self.harness.add_relation_unit(relation_id, "magma-orc8r-certifier/0")
            relation_id = self.harness.add_relation("obsidian", "magma-orc8r-obsidian")
            self.harness.add_relation_unit(relation_id, "magma-orc8r-obsidian/0")
            with patch(
                "charm.MagmaOrc8rNginxCharm._get_domain_name", new_callable=PropertyMock
            ) as domain_name, patch(
                "charm.MagmaOrc8rNginxCharm._create_additional_orc8r_nginx_services",
                new_callable=PropertyMock,
            ) as create_additional_orc8r_nginx_services:
                domain_name.return_value = "test.domain.com"
                create_additional_orc8r_nginx_services.return_value = Mock()
                self.harness.charm.on.magma_orc8r_nginx_pebble_ready.emit(event)
        mock.assert_called_once()

    """
    def test(  # noqa: E501
        self,
    ):
        event = Mock()
        with patch("ops.model.Container.exec") as exec, patch(
            "charm.MagmaOrc8rNginxCharm._relations_ready", new_callable=PropertyMock
        ) as relations_ready:
            exec.return_value = MockExec()
            relations_ready.return_value=True
            with patch(
                "charm.MagmaOrc8rNginxCharm._get_domain_name", new_callable=PropertyMock
            ) as domain_name, patch(
                "charm.MagmaOrc8rNginxCharm._create_additional_orc8r_nginx_services",
                new_callable=PropertyMock,
            ) as create_additional_orc8r_nginx_services, patch(
                "ops.model.Container.can_connect"
            ) as can_connect, patch(
                "ops.model.Container.get_plan"
            ) as get_plan:
                get_plan.return_value = Mock()
                domain_name.return_value = "test.domain.com"
                create_additional_orc8r_nginx_services.return_value = Mock()
                can_connect.return_value=True
                self.harness.charm.on.magma_orc8r_nginx_pebble_ready.emit(event)
        exec.assert_called_once()
        """
