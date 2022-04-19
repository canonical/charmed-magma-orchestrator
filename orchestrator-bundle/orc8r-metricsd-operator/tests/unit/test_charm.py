#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import PropertyMock, call, patch

from ops import testing
from ops.model import BlockedStatus

from charm import MagmaOrc8rMetricsdCharm

testing.SIMULATE_CAN_CONNECT = True


class MockModel:
    def __init__(self, name: str):
        self._name = name

    @property
    def name(self):
        return self._name


class TestCharm(unittest.TestCase):
    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports, additional_labels, additional_annotations: None,
    )
    def setUp(self):
        self.harness = testing.Harness(MagmaOrc8rMetricsdCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch("ops.model.Container.push")
    def test_given_new_charm_when_on_install_event_then_config_file_is_created(self, patch_push):
        self.harness.charm.on.install.emit()

        calls = [
            call(
                "/var/opt/magma/configs/orc8r/metricsd.yml",
                'prometheusQueryAddress: "http://orc8r-prometheus:9090"\n'
                'alertmanagerApiURL: "http://orc8r-alertmanager:9093/api/v2"\n'
                'prometheusConfigServiceURL: "http://orc8r-prometheus:9100/v1"\n'
                'alertmanagerConfigServiceURL: "http://orc8r-alertmanager:9101/v1"\n'
                '"profile": "prometheus"\n',
            ),
        ]
        patch_push.assert_has_calls(calls)

    def test_given_relation_with_service_registry_doesnt_exist_when_pebble_ready_then_app_status_is_blocked(  # noqa: E501
        self,
    ):
        container_name = "magma-orc8r-metricsd"

        self.harness.container_pebble_ready(container_name=container_name)

        assert self.harness.charm.unit.status == BlockedStatus(
            "Waiting for service registry relation to be created"
        )

    @patch("charm.MagmaOrc8rMetricsdCharm._namespace", new_callable=PropertyMock)
    def test_given_pebble_ready_when_service_registry_relation_joined_then_pebble_plan_is_created_successfully(  # noqa: E501
        self, patch_namespace
    ):
        container_name = "magma-orc8r-metricsd"
        namespace = "whatever"
        patch_namespace.return_value = namespace
        self.harness.container_pebble_ready(container_name=container_name)

        relation_id = self.harness.add_relation(
            relation_name="magma-service-registry", remote_app="orc8r-service-registry"
        )
        self.harness.add_relation_unit(
            relation_id=relation_id, remote_unit_name="orc8r-service-registry/0"
        )

        pebble_plan = self.harness.get_container_pebble_plan(container_name).to_dict()
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
                        "SERVICE_REGISTRY_NAMESPACE": namespace,
                    },
                }
            },
        }
        assert pebble_plan == expected_plan
