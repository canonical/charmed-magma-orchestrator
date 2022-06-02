# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch

from ops import testing
from ops.model import BlockedStatus
from ops.pebble import APIError

from charm import MagmaOrc8rOrchestratorCharm

testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports, additional_labels, additional_annotations: None,
    )
    def setUp(self):
        self.model_name = "whatever name"
        self.harness = testing.Harness(MagmaOrc8rOrchestratorCharm)
        self.harness.set_model_name(name=self.model_name)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch("ops.model.Container.exists")
    def test_given_relations_created_when_pebble_ready_then_service_is_added_to_pebble_plan(
        self, file_exists
    ):
        file_exists.return_value = True
        relation_id = self.harness.add_relation(
            relation_name="admin-operator", remote_app="whatever"
        )
        self.harness.add_relation_unit(relation_id=relation_id, remote_unit_name="whatever/0")
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
                        "SERVICE_REGISTRY_NAMESPACE": self.model_name,
                    },
                },
            },
        }

        self.harness.container_pebble_ready("magma-orc8r-orchestrator")

        updated_plan = self.harness.get_container_pebble_plan("magma-orc8r-orchestrator").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    @patch("ops.model.Container.push")
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

    def test_given_default_elasticsearch_config_when_on_config_changed_event_then_status_is_blocked(  # noqa: E501
        self,
    ):
        key_values = {"elasticsearch-url": ""}
        self.harness.container_pebble_ready("magma-orc8r-orchestrator")
        self.harness.update_config(key_values=key_values)

        assert self.harness.charm.unit.status == BlockedStatus(
            "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
        )

    @patch("ops.model.Container.restart")
    @patch("ops.model.Container.push")
    def test_given_good_elasticsearch_config_when_on_config_changed_event_then_elasticsearch_config_file_is_created(  # noqa: E501
        self, patch_push, patch_restart
    ):
        patch_restart.side_effect = APIError(
            body={"bla": "blo"},
            code=400,
            status="whatever status",
            message="whatever message",
        )
        hostname = "blablabla"
        port = 80
        config = {"elasticsearch-url": f"{hostname}:{port}"}
        self.harness.container_pebble_ready("magma-orc8r-orchestrator")

        self.harness.update_config(key_values=config)

        patch_push.assert_any_call(
            "/var/opt/magma/configs/orc8r/elastic.yml",
            f'"elasticHost": "{hostname}"\n' f'"elasticPort": {port}\n',
        )

    @patch("ops.model.Container.push")
    def test_given_bad_elasticsearch_config_when_on_config_changed_event_then_status_is_blocked(
        self, _
    ):
        config = {"elasticsearch-url": "hello"}
        self.harness.container_pebble_ready("magma-orc8r-orchestrator")

        self.harness.update_config(key_values=config)

        assert self.harness.charm.unit.status == BlockedStatus(
            "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
        )
