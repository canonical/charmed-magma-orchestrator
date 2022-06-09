# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, PropertyMock, patch

import httpx
from lightkube.core.exceptions import ApiError
from lightkube.models.core_v1 import (
    LoadBalancerIngress,
    LoadBalancerStatus,
    Service,
    ServiceStatus,
)
from ops import testing
from ops.model import ActiveStatus, BlockedStatus

from charm import MagmaOrc8rOrchestratorCharm

testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    @staticmethod
    def k8s_load_balancer_service(ip: str) -> Service:
        return Service(
            apiVersion="v1",
            kind="Service",
            status=ServiceStatus(
                loadBalancer=LoadBalancerStatus(
                    ingress=[
                        LoadBalancerIngress(
                            ip=ip,
                        )
                    ]
                )
            ),
        )

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
    @patch("charm.MagmaOrc8rOrchestratorCharm._relations_ready", PropertyMock(return_value=True))
    def test_given_pebble_ready_when_on_install_event_then_orchestrator_config_file_is_created(  # noqa: E501
        self, patch_push
    ):
        self.harness.container_pebble_ready("magma-orc8r-orchestrator")
        self.harness.charm.on.install.emit()

        patch_push.assert_any_call(
            "/var/opt/magma/configs/orc8r/orchestrator.yml",
            '"prometheusGRPCPushAddress": "orc8r-prometheus-cache:9092"\n'
            '"prometheusPushAddresses":\n'
            '- "http://orc8r-prometheus-cache:9091/metrics"\n'
            '"useGRPCExporter": true\n',
        )

    @patch("ops.model.Container.push")
    @patch("charm.MagmaOrc8rOrchestratorCharm._relations_ready", PropertyMock(return_value=True))
    def test_given_new_charm_when_on_install_event_then_metricsd_config_file_is_created(
        self, patch_push
    ):
        self.harness.container_pebble_ready("magma-orc8r-orchestrator")
        self.harness.charm.on.install.emit()

        patch_push.assert_any_call(
            "/var/opt/magma/configs/orc8r/metricsd.yml",
            'prometheusQueryAddress: "http://orc8r-prometheus:9090"\n'
            'alertmanagerApiURL: "http://orc8r-alertmanager:9093/api/v2"\n'
            'prometheusConfigServiceURL: "http://orc8r-prometheus:9100/v1"\n'
            'alertmanagerConfigServiceURL: "http://orc8r-alertmanager:9101/v1"\n'
            '"profile": "prometheus"\n',
        )

    @patch("ops.model.Container.push")
    @patch("charm.MagmaOrc8rOrchestratorCharm._relations_ready", PropertyMock(return_value=True))
    def test_given_new_charm_when_on_install_event_then_analytics_config_file_is_created(
        self, patch_push
    ):
        self.harness.container_pebble_ready("magma-orc8r-orchestrator")
        self.harness.charm.on.install.emit()

        patch_push.assert_any_call(
            "/var/opt/magma/configs/orc8r/analytics.yml",
            '"appID": ""\n'
            '"appSecret": ""\n'
            '"categoryName": "magma"\n'
            '"exportMetrics": false\n'
            '"metricExportURL": ""\n'
            '"metricsPrefix": ""\n',
        )

    @patch("charm.MagmaOrc8rOrchestratorCharm._relations_ready", PropertyMock(return_value=True))
    def test_given_default_elasticsearch_config_when_on_config_changed_event_then_status_is_blocked(  # noqa: E501
        self,
    ):
        key_values = {"elasticsearch-url": ""}
        self.harness.container_pebble_ready("magma-orc8r-orchestrator")
        self.harness.update_config(key_values=key_values)

        assert self.harness.charm.unit.status == BlockedStatus(
            "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
        )

    @patch("ops.model.Container.push")
    @patch("ops.model.Container.restart", Mock())
    @patch("charm.MagmaOrc8rOrchestratorCharm._relations_ready", PropertyMock(return_value=True))
    def test_given_good_elasticsearch_config_when_on_config_changed_event_then_elasticsearch_config_file_is_created(  # noqa: E501
        self, patch_push
    ):
        hostname = "blablabla"
        port = 80
        config = {"elasticsearch-url": f"{hostname}:{port}"}
        self.harness.container_pebble_ready("magma-orc8r-orchestrator")

        self.harness.update_config(key_values=config)

        patch_push.assert_any_call(
            "/var/opt/magma/configs/orc8r/elastic.yml",
            f'"elasticHost": "{hostname}"\n' f'"elasticPort": {port}\n',
        )
        assert self.harness.charm.unit.status == ActiveStatus()

    @patch("ops.model.Container.push")
    @patch("charm.MagmaOrc8rOrchestratorCharm._relations_ready", PropertyMock(return_value=True))
    def test_given_bad_elasticsearch_config_when_on_config_changed_event_then_status_is_blocked(
        self, _
    ):
        config = {"elasticsearch-url": "hello"}
        self.harness.container_pebble_ready("magma-orc8r-orchestrator")

        self.harness.update_config(key_values=config)

        assert self.harness.charm.unit.status == BlockedStatus(
            "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
        )

    @patch("lightkube.Client.get")
    @patch("lightkube.core.client.GenericSyncClient")
    def test_given_k8s_services_exist_when_get_load_balancer_services_action_then_services_are_returned(  # noqa: E501
        self, _, patch_k8s_get
    ):
        event = Mock()
        ip_1 = "whatever ip 1"
        ip_2 = "whatever ip 2"
        ip_3 = "whatever ip 3"
        ip_4 = "whatever ip 4"
        service_1 = self.k8s_load_balancer_service(ip=ip_1)
        service_2 = self.k8s_load_balancer_service(ip=ip_2)
        service_3 = self.k8s_load_balancer_service(ip=ip_3)
        service_4 = self.k8s_load_balancer_service(ip=ip_4)
        patch_k8s_get.side_effect = [service_1, service_2, service_3, service_4]

        self.harness.charm._on_get_load_balancer_services_action(event)

        event.set_results.assert_called_with(
            {
                "nginx-proxy": ip_1,
                "orc8r-clientcert-nginx": ip_2,
                "orc8r-nginx-proxy": ip_3,
                "orc8r-bootstrap-nginx": ip_4,
            }
        )

    @patch("lightkube.Client.get")
    @patch("lightkube.core.client.GenericSyncClient")
    def test_given_k8s_api_exception_when_get_load_balancer_services_action_then_service_ips_are_returned_with_na(  # noqa: E501
        self, _, patch_k8s_get
    ):
        event = Mock()
        api_error = ApiError(response=httpx.Response(status_code=400, json={"key": "value"}))
        patch_k8s_get.side_effect = [api_error, api_error, api_error, api_error]

        self.harness.charm._on_get_load_balancer_services_action(event)

        event.set_results.assert_called_with(
            {
                "nginx-proxy": "NA",
                "orc8r-clientcert-nginx": "NA",
                "orc8r-nginx-proxy": "NA",
                "orc8r-bootstrap-nginx": "NA",
            }
        )
