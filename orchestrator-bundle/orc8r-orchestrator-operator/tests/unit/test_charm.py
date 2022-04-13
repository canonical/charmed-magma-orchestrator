# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, PropertyMock, call, patch

from ops import testing

from charm import MagmaOrc8rOrchestratorCharm

testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports, additional_labels, additional_annotations: None,
    )
    def setUp(self):
        self.harness = testing.Harness(MagmaOrc8rOrchestratorCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch("charm.MagmaOrc8rOrchestratorCharm._namespace", new_callable=PropertyMock)
    @patch("charm.MagmaOrc8rOrchestratorCharm._relations_ready")
    def test_given_ready_when_get_plan_then_plan_is_filled_with_magma_nms_magmalte_service_content(
        self, relations_ready, patch_namespace
    ):
        namespace = "whatever"
        relations_ready.return_value = True
        patch_namespace.return_value = namespace
        expected_plan = {
            "services": {
                "magma-orc8r-orchestrator": {
                    "startup": "enabled",
                    "override": "replace",
                    "command": "/usr/bin/envdir "
                    "/var/opt/magma/envdir "
                    "/var/opt/magma/bin/orchestrator "
                    "-run_echo_server=true "
                    "-logtostderr=true -v=0",
                    "environment": {
                        "SERVICE_HOSTNAME": "magma-orc8r-orchestrator",
                        "SERVICE_REGISTRY_MODE": "k8s",
                        "SERVICE_REGISTRY_NAMESPACE": namespace,
                    },
                },
            },
        }
        self.harness.container_pebble_ready("magma-orc8r-orchestrator")
        updated_plan = self.harness.get_container_pebble_plan("magma-orc8r-orchestrator").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    @patch("ops.model.Container.push")
    def test_given_new_charm_when_on_install_event_then_config_file_is_created(self, patch_push):
        event = Mock()

        self.harness.charm._on_install(event)

        calls = [
            call(
                "/var/opt/magma/configs/orc8r/orchestrator.yml",
                '"prometheusGRPCPushAddress": "orc8r-prometheus-cache:9092"\n'
                '"prometheusPushAddresses":\n'
                '- "http://orc8r-prometheus-cache:9091/metrics"\n'
                '"useGRPCExporter": true\n',
            ),
            call(
                "/var/opt/magma/configs/orc8r/metricsd.yml",
                'prometheusQueryAddress: "http://orc8r-prometheus:9090"\n'
                'alertmanagerApiURL: "http://orc8r-alertmanager:9093/api/v2"\n'
                'prometheusConfigServiceURL: "http://orc8r-prometheus:9100/v1"\n'
                'alertmanagerConfigServiceURL: "http://orc8r-alertmanager:9101/v1"\n'
                '"profile": "prometheus"\n',
            ),
            call(
                "/var/opt/magma/configs/orc8r/analytics.yml",
                '"appID": ""\n'
                '"appSecret": ""\n'
                '"categoryName": "magma"\n'
                '"exportMetrics": false\n'
                '"metricExportURL": ""\n'
                '"metricsPrefix": ""\n',
            ),
            call(
                "/var/opt/magma/configs/orc8r/elastic.yml",
                '"elasticHost": "orc8r-elasticsearch"\n' '"elasticPort": 80\n',
            ),
        ]
        patch_push.assert_has_calls(calls)
