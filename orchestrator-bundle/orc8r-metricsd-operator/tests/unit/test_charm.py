#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import call, patch

from ops import testing
from ops.model import BlockedStatus, WaitingStatus

from charm import MagmaOrc8rMetricsdCharm

testing.SIMULATE_CAN_CONNECT = True


class MockModel:
    def __init__(self, name: str):
        self._name = name

    @property
    def name(self):
        return self._name


class TestCharm(unittest.TestCase):
    """Placeholder tests.

    Unit tests for charms that leverage the `orc8r_base` and `orc8r_base_db` libraries are
    done at the library level. This file only contains tests for additional functionality not
    present in the base libraries.
    """

    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports, additional_labels, additional_annotations: None,
    )
    def setUp(self):
        self.harness = testing.Harness(MagmaOrc8rMetricsdCharm)
        self.harness.set_can_connect("magma-orc8r-metricsd", True)
        self.container = self.harness.model.unit.get_container("magma-orc8r-metricsd")
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_given_no_relations_created_when_pebble_ready_then_charm_goes_to_blocked_status(self):
        self.harness.charm.on.magma_orc8r_metricsd_pebble_ready.emit(self.container)
        assert self.harness.charm.unit.status == BlockedStatus(
            "Waiting for relation(s) to be created: magma-orc8r-orchestrator"
        )

    def test_given_all_relations_created_when_pebble_ready_then_charm_goes_to_waiting_status(self):
        orchestrator_relation_id = self.harness.add_relation(
            relation_name="magma-orc8r-orchestrator", remote_app="orchestrator"
        )
        self.harness.add_relation_unit(
            relation_id=orchestrator_relation_id, remote_unit_name="orchestrator/0"
        )
        self.harness.charm.on.magma_orc8r_metricsd_pebble_ready.emit(self.container)
        assert self.harness.charm.unit.status == WaitingStatus(
            "Waiting for relation(s) to be ready: magma-orc8r-orchestrator"
        )

    def test_given_no_relations_created_created_when_install_then_charm_goes_to_blocked_status(
        self
    ):
        self.harness.charm.on.install.emit()
        assert self.harness.charm.unit.status == BlockedStatus(
            "Waiting for relation(s) to be created: alertmanager-k8s, prometheus-k8s, "
            "prometheus-configurer-k8s"
        )

    @patch("ops.model.Container.push")
    def test_given_new_charm_when_on_install_event_then_config_file_is_created(self, patch_push):
        test_alertmanager_app_name = "test-alertmanager"
        test_prometheus_app_name = "test-prometheus"
        test_prometheus_configurer_app_name = "test-prometheus-configurer"
        alertmanager_relation_id = self.harness.add_relation(
            relation_name="alertmanager-k8s", remote_app=test_alertmanager_app_name
        )
        self.harness.add_relation_unit(
            relation_id=alertmanager_relation_id,
            remote_unit_name=f"{test_alertmanager_app_name}/0",
        )
        prometheus_relation_id = self.harness.add_relation(
            relation_name="prometheus-k8s", remote_app=test_prometheus_app_name
        )
        self.harness.add_relation_unit(
            relation_id=prometheus_relation_id, remote_unit_name=f"{test_prometheus_app_name}/0"
        )
        prometheus_configurer_relation_id = self.harness.add_relation(
            relation_name="prometheus-configurer-k8s",
            remote_app=test_prometheus_configurer_app_name,
        )
        self.harness.add_relation_unit(
            relation_id=prometheus_configurer_relation_id,
            remote_unit_name=f"{test_prometheus_configurer_app_name}/0",
        )
        self.harness.charm.on.install.emit()

        calls = [
            call(
                "/var/opt/magma/configs/orc8r/metricsd.yml",
                f'prometheusQueryAddress: "http://{test_prometheus_app_name}:9090"\n'
                f'alertmanagerApiURL: "http://{test_alertmanager_app_name}:9093/api/v2"\n'
                "prometheusConfigServiceURL: "
                f'"http://{test_prometheus_configurer_app_name}:9100/v1"\n'
                'alertmanagerConfigServiceURL: "http://orc8r-alertmanager:9101/v1"\n'
                '"profile": "prometheus"\n',
            ),
        ]
        patch_push.assert_has_calls(calls)
