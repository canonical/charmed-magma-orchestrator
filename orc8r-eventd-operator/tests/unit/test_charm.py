#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, call, patch

from ops import testing
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

from charm import MagmaOrc8rEventdCharm


class TestCharm(unittest.TestCase):
    """Eventd unit tests."""

    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports, additional_labels, additional_annotations: None,
    )
    def setUp(self):
        self.namespace = "whatever"
        self.harness = testing.Harness(MagmaOrc8rEventdCharm)
        self.harness.set_model_name(name=self.namespace)
        self.addCleanup(self.harness.cleanup)
        self.container = self.harness.model.unit.get_container("magma-orc8r-eventd")
        self.harness.begin()

    def test_given_container_not_ready_when_install_then_status_is_waiting(self):
        self.harness.set_can_connect(self.container, False)
        self.harness.charm.on.install.emit()

        assert self.harness.charm.unit.status == WaitingStatus("Waiting for container to be ready")

    def test_given_no_elasticsearch_config_when_install_then_status_is_blocked(self):
        self.harness.set_can_connect(self.container, True)
        self.harness.charm.on.install.emit()

        assert self.harness.charm.unit.status == BlockedStatus(
            "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
        )

    @patch("ops.model.Container.push")
    def test_given_valid_elasticsearch_config_when_install_then_elasticsearch_config_file_is_pushed_to_workload_container(  # noqa: E501
        self, patched_push
    ):
        hostname = "blablabla"
        port = 80
        valid_es_config = {"elasticsearch-url": f"{hostname}:{port}"}
        self.harness.set_can_connect(self.container, True)
        self.harness.update_config(key_values=valid_es_config)

        self.harness.charm.on.install.emit()

        calls = [
            call(
                "/var/opt/magma/configs/orc8r/elastic.yml",
                f'"elasticHost": "{hostname}"\n' f'"elasticPort": {port}\n',
            ),
        ]
        patched_push.assert_has_calls(calls)

    def test_given_no_elasticsearch_config_when_pebble_ready_then_status_is_waiting(self):
        self.harness.charm.on.magma_orc8r_eventd_pebble_ready.emit(self.container)

        assert self.harness.charm.unit.status == BlockedStatus(
            "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
        )

    @patch("ops.model.Container.push")
    def test_given_valid_elasticsearch_config_when_pebble_ready_then_elasticsearch_config_file_is_pushed_to_workload_container(  # noqa: E501
        self, patched_push
    ):
        hostname = "blablabla"
        port = 80
        valid_es_config = {"elasticsearch-url": f"{hostname}:{port}"}
        self.harness.set_can_connect(self.container, True)
        self.harness.update_config(key_values=valid_es_config)

        self.harness.charm.on.magma_orc8r_eventd_pebble_ready.emit(self.container)

        calls = [
            call(
                "/var/opt/magma/configs/orc8r/elastic.yml",
                f'"elasticHost": "{hostname}"\n' f'"elasticPort": {port}\n',
            ),
        ]
        patched_push.assert_has_calls(calls)

    @patch("ops.model.Container.push", Mock())
    def test_given_valid_elasticsearch_config_when_pebble_ready_then_pebble_plan_is_updated_with_correct_pebble_layer(  # noqa: E501
        self,
    ):
        hostname = "blablabla"
        port = 80
        valid_es_config = {"elasticsearch-url": f"{hostname}:{port}"}
        self.harness.set_can_connect(self.container, True)
        self.harness.update_config(key_values=valid_es_config)
        expected_plan = {
            "services": {
                "magma-orc8r-eventd": {
                    "override": "replace",
                    "summary": "magma-orc8r-eventd",
                    "startup": "enabled",
                    "command": "/usr/bin/envdir "
                    "/var/opt/magma/envdir "
                    "/var/opt/magma/bin/eventd "
                    "-run_echo_server=true "
                    "-logtostderr=true "
                    "-v=0",
                    "environment": {
                        "SERVICE_HOSTNAME": "magma-orc8r-eventd",
                        "SERVICE_REGISTRY_MODE": "k8s",
                        "SERVICE_REGISTRY_NAMESPACE": self.namespace,
                    },
                }
            },
        }

        self.harness.charm.on.magma_orc8r_eventd_pebble_ready.emit(self.container)

        updated_plan = self.harness.get_container_pebble_plan("magma-orc8r-eventd").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    @patch("ops.model.Container.push", Mock())
    def test_given_valid_elasticsearch_config_when_pebble_ready_then_status_is_active(self):
        hostname = "blablabla"
        port = 80
        valid_es_config = {"elasticsearch-url": f"{hostname}:{port}"}
        self.harness.set_can_connect(self.container, True)
        self.harness.update_config(key_values=valid_es_config)

        self.harness.charm.on.magma_orc8r_eventd_pebble_ready.emit(self.container)

        assert self.harness.charm.unit.status == ActiveStatus()

    def test_given_eventd_service_not_running_when_eventd_relation_joined_then_service_active_status_in_the_relation_data_bag_is_false(  # noqa: E501
        self,
    ):
        self.harness.set_leader(True)
        relation_id = self.harness.add_relation("magma-orc8r-eventd", self.harness.charm.app.name)
        self.harness.add_relation_unit(relation_id, self.harness.charm.unit.name)

        self.assertEqual(
            self.harness.get_relation_data(relation_id, self.harness.charm.unit.name),
            {"active": "False"},
        )

    @patch("ops.model.Container.push", Mock())
    def test_given_eventd_service_running_when_eventd_relation_joined_then_service_active_status_in_the_relation_data_bag_is_true(  # noqa: E501
        self,
    ):
        self.harness.set_leader(True)
        hostname = "blablabla"
        port = 80
        valid_es_config = {"elasticsearch-url": f"{hostname}:{port}"}
        self.harness.set_can_connect(self.container, True)
        self.harness.update_config(key_values=valid_es_config)
        self.harness.charm.on.magma_orc8r_eventd_pebble_ready.emit(self.container)

        relation_id = self.harness.add_relation("magma-orc8r-eventd", self.harness.charm.app.name)
        self.harness.add_relation_unit(relation_id, self.harness.charm.unit.name)

        self.assertEqual(
            self.harness.get_relation_data(relation_id, self.harness.charm.unit.name),
            {"active": "True"},
        )

    def test_given_default_config_when_config_changed_then_status_is_blocked(self):
        key_values = {"elasticsearch-url": ""}
        self.harness.container_pebble_ready("magma-orc8r-eventd")

        self.harness.update_config(key_values=key_values)

        assert self.harness.charm.unit.status == BlockedStatus(
            "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
        )

    @patch("ops.model.Container.push")
    def test_given_good_elasticsearch_config_when_config_changed_then_config_is_written_to_file(
        self, patch_push
    ):
        hostname = "blablabla"
        port = 80
        config = {"elasticsearch-url": f"{hostname}:{port}"}

        self.harness.container_pebble_ready("magma-orc8r-eventd")
        self.harness.update_config(key_values=config)

        calls = [
            call(
                "/var/opt/magma/configs/orc8r/elastic.yml",
                f'"elasticHost": "{hostname}"\n' f'"elasticPort": {port}\n',
            ),
        ]
        patch_push.assert_has_calls(calls)

    def test_given_bad_elasticsearch_config_when_config_changed_then_status_is_blocked(self):
        config = {"elasticsearch-url": "hello"}

        self.harness.container_pebble_ready("magma-orc8r-eventd")
        self.harness.update_config(key_values=config)

        assert self.harness.charm.unit.status == BlockedStatus(
            "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
        )
