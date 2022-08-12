#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, call, patch

from ops import testing
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

from charm import MagmaOrc8rMetricsdCharm

testing.SIMULATE_CAN_CONNECT = True


class MockModel:
    def __init__(self, name: str):
        self._name = name

    @property
    def name(self):
        return self._name


class TestCharm(unittest.TestCase):
    """Metricsd unit tests."""

    TEST_ALERTMANAGER_APP_NAME = "test-alertmanager"
    TEST_PROMETHEUS_APP_NAME = "test-prometheus"
    TEST_PROMETHEUS_CONFIGURER_APP_NAME = "test-prometheus-configurer"
    TEST_ORC8R_ORCHESTRATOR_APP_NAME = "test-orc8r-orchestrator"

    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports, additional_labels, additional_annotations: None,
    )
    def setUp(self):
        self.namespace = "whatever"
        self.harness = testing.Harness(MagmaOrc8rMetricsdCharm)
        self.harness.set_model_name(name=self.namespace)
        self.harness.set_can_connect("magma-orc8r-metricsd", True)
        self.container = self.harness.model.unit.get_container("magma-orc8r-metricsd")
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_given_no_relations_created_when_pebble_ready_then_charm_goes_to_blocked_status(self):
        self.harness.charm.on.magma_orc8r_metricsd_pebble_ready.emit(self.container)
        assert self.harness.charm.unit.status == BlockedStatus(
            "Waiting for relation(s) to be created: alertmanager-k8s, prometheus-k8s, "
            "prometheus-configurer-k8s, magma-orc8r-orchestrator"
        )

    @patch("ops.model.Container.push")
    def test_given_all_relations_created_when_pebble_ready_then_config_file_is_created(
        self, patch_push
    ):
        expected_calls = [
            call(
                "/var/opt/magma/configs/orc8r/metricsd.yml",
                f'prometheusQueryAddress: "http://{self.TEST_PROMETHEUS_APP_NAME}:9090"\n'
                f'alertmanagerApiURL: "http://{self.TEST_ALERTMANAGER_APP_NAME}:9093/api/v2"\n'
                "prometheusConfigServiceURL: "
                f'"http://{self.TEST_PROMETHEUS_CONFIGURER_APP_NAME}:9100/v1"\n'
                'alertmanagerConfigServiceURL: "http://orc8r-alertmanager:9101/v1"\n'
                '"profile": "prometheus"\n',
            ),
        ]
        self._create_relations()

        self.harness.charm.on.magma_orc8r_metricsd_pebble_ready.emit(self.container)

        patch_push.assert_has_calls(expected_calls)

    @patch("ops.model.Container.push", Mock())
    def test_given_all_relations_created_when_pebble_ready_then_charm_goes_to_waiting_status(
        self,
    ):
        self._create_relations()

        self.harness.charm.on.magma_orc8r_metricsd_pebble_ready.emit(self.container)

        assert self.harness.charm.unit.status == WaitingStatus(
            "Waiting for relation(s) to be ready: magma-orc8r-orchestrator"
        )

    @patch("ops.model.Container.push", Mock())
    def test_given_all_relations_created_and_ready_but_container_not_reachable_when_pebble_ready_then_charm_goes_to_waiting_status(  # noqa: E501
        self,
    ):
        self._create_relations(activate=True)
        self.harness.set_can_connect("magma-orc8r-metricsd", False)

        self.harness.charm.on.magma_orc8r_metricsd_pebble_ready.emit(self.container)

        assert self.harness.charm.unit.status == WaitingStatus("Waiting for container to be ready")

    @patch("ops.model.Container.push", Mock())
    def test_given_all_relations_created_and_ready_and_container_reachable_when_pebble_ready_then_charm_goes_to_active_status(  # noqa: E501
        self,
    ):
        self._create_relations(activate=True)

        self.harness.charm.on.magma_orc8r_metricsd_pebble_ready.emit(self.container)

        assert self.harness.charm.unit.status == ActiveStatus()

    @patch("ops.model.Container.push", Mock())
    def test_given_all_relations_created_and_ready_and_container_reachable_when_pebble_ready_then_ebble_plan_is_updated_with_correct_pebble_layer(  # noqa: E501
        self,
    ):
        expected_plan = {
            "services": {
                "magma-orc8r-metricsd": {
                    "override": "replace",
                    "summary": "magma-orc8r-metricsd",
                    "startup": "enabled",
                    "command": "/usr/bin/envdir "
                    "/var/opt/magma/envdir "
                    "/var/opt/magma/bin/metricsd "
                    "-run_echo_server=true "
                    "-logtostderr=true "
                    "-v=0",
                    "environment": {
                        "SERVICE_HOSTNAME": "magma-orc8r-metricsd",
                        "SERVICE_REGISTRY_MODE": "k8s",
                        "SERVICE_REGISTRY_NAMESPACE": self.namespace,
                    },
                }
            },
        }
        self._create_relations(activate=True)

        self.harness.charm.on.magma_orc8r_metricsd_pebble_ready.emit(self.container)

        updated_plan = self.harness.get_container_pebble_plan("magma-orc8r-metricsd").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    def test_given_metricsd_service_not_running_when_metricsd_relation_joined_then_service_active_status_in_the_relation_data_bag_is_false(  # noqa: E501
        self,
    ):
        self.harness.set_leader(True)
        relation_id = self.harness.add_relation("magma-orc8r-metricsd", "orc8r-metricsd")
        self.harness.add_relation_unit(relation_id, "magma-orc8r-metricsd/0")

        self.assertEqual(
            self.harness.get_relation_data(relation_id, "magma-orc8r-metricsd/0"),
            {"active": "False"},
        )

    @patch("ops.model.Container.push", Mock())
    def test_given_metricsd_service_running_when_metricsd_relation_joined_then_service_active_status_in_the_relation_data_bag_is_true(  # noqa: E501
        self,
    ):
        self.harness.set_leader(True)
        self._create_relations(activate=True)
        self.harness.charm.on.magma_orc8r_metricsd_pebble_ready.emit(self.container)

        relation_id = self.harness.add_relation("magma-orc8r-metricsd", "orc8r-metricsd")
        self.harness.add_relation_unit(relation_id, "magma-orc8r-metricsd/0")

        self.assertEqual(
            self.harness.get_relation_data(relation_id, "magma-orc8r-metricsd/0"),
            {"active": "True"},
        )

    def _create_relations(self, activate=False):
        alertmanager_relation_id = self.harness.add_relation(
            relation_name="alertmanager-k8s", remote_app=self.TEST_ALERTMANAGER_APP_NAME
        )
        self.harness.add_relation_unit(
            relation_id=alertmanager_relation_id,
            remote_unit_name=f"{self.TEST_ALERTMANAGER_APP_NAME}/0",
        )
        prometheus_relation_id = self.harness.add_relation(
            relation_name="prometheus-k8s", remote_app=self.TEST_PROMETHEUS_APP_NAME
        )
        self.harness.add_relation_unit(
            relation_id=prometheus_relation_id,
            remote_unit_name=f"{self.TEST_PROMETHEUS_APP_NAME}/0",
        )
        prometheus_configurer_relation_id = self.harness.add_relation(
            relation_name="prometheus-configurer-k8s",
            remote_app=self.TEST_PROMETHEUS_CONFIGURER_APP_NAME,
        )
        self.harness.add_relation_unit(
            relation_id=prometheus_configurer_relation_id,
            remote_unit_name=f"{self.TEST_PROMETHEUS_CONFIGURER_APP_NAME}/0",
        )
        orc8r_orchestrator_relation_id = self.harness.add_relation(
            relation_name="magma-orc8r-orchestrator",
            remote_app=self.TEST_ORC8R_ORCHESTRATOR_APP_NAME,
        )
        self.harness.add_relation_unit(
            relation_id=orc8r_orchestrator_relation_id,
            remote_unit_name=f"{self.TEST_ORC8R_ORCHESTRATOR_APP_NAME}/0",
        )
        if activate:
            self.harness.update_relation_data(
                relation_id=orc8r_orchestrator_relation_id,
                app_or_unit=f"{self.TEST_ORC8R_ORCHESTRATOR_APP_NAME}/0",
                key_values={"active": "True"},
            )
