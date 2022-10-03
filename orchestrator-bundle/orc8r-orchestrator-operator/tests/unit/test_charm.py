# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, call, patch

from lightkube.models.core_v1 import (
    LoadBalancerIngress,
    LoadBalancerStatus,
    Service,
    ServiceStatus,
)
from lightkube.models.meta_v1 import ObjectMeta
from ops import testing
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

from charm import MagmaOrc8rOrchestratorCharm

testing.SIMULATE_CAN_CONNECT = True


class MockExec:
    def __init__(self, *args, **kwargs):
        pass

    def exec(self, *args, **kwargs):
        pass

    def wait_output(self, *args, **kwargs):
        return "test stdout", "test err"


class TestCharm(unittest.TestCase):
    @staticmethod
    def k8s_load_balancer_service(ip: str, name: str) -> Service:
        return Service(
            metadata=ObjectMeta(name=name),
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
        self.namespace = "whatever"
        self.harness = testing.Harness(MagmaOrc8rOrchestratorCharm)
        self.harness.set_model_name(name=self.namespace)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch("ops.model.Container.exec", new_callable=Mock)
    @patch("ops.model.Container.exists", new=Mock())
    def test_given_relations_created_and_certs_are_mounted_when_pebble_ready_then_pebble_plan_containing_workload_service_is_created(  # noqa: E501
        self, patch_exec
    ):
        patch_exec.return_value = MockExec()
        self.harness.add_relation(
            relation_name="cert-admin-operator", remote_app="orc8r-certifier"
        )
        self._create_relations()
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
                        "SERVICE_REGISTRY_NAMESPACE": self.namespace,
                    },
                },
            },
        }

        self.harness.container_pebble_ready("magma-orc8r-orchestrator")

        updated_plan = self.harness.get_container_pebble_plan("magma-orc8r-orchestrator").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    @patch("ops.model.Container.push")
    def test_given_pebble_ready_when_on_install_event_then_orchestrator_config_file_is_created(  # noqa: E501
        self,
        patch_push,
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
        self,
        patch_push,
    ):
        self.harness.container_pebble_ready("magma-orc8r-orchestrator")
        self.harness.charm.on.install.emit()

        patch_push.assert_any_call(
            "/var/opt/magma/configs/orc8r/metricsd.yml",
            'prometheusQueryAddress: "http://orc8r-prometheus:9090"\n'
            'alertmanagerApiURL: "http://orc8r-alertmanager:9093/api/v2"\n'
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

    @patch("ops.model.Container.exists", new=Mock())
    @patch("ops.model.Container.exec", new_callable=Mock)
    @patch("ops.model.Container.push", new=Mock())
    def test_given_relations_ready_and_container_can_connect_and_unit_is_leader_when_on_pebble_ready_event_then_orchestrator_admin_user_is_created(  # noqa: E501
        self, patch_exec
    ):
        patch_exec.return_value = MockExec()
        self.harness.set_leader(True)

        self.harness.add_relation(
            relation_name="cert-admin-operator", remote_app="orc8r-certifier"
        )
        self._create_relations()
        self.harness.container_pebble_ready("magma-orc8r-orchestrator")

        args, _ = patch_exec.call_args
        patch_exec.assert_called_once()
        call_command = [
            "/var/opt/magma/bin/accessc",
            "add-existing",
            "-admin",
            "-cert",
            "/var/opt/magma/certs/admin_operator.pem",
            "admin_operator",
        ]
        self.assertIn(call_command, args)

    @patch("ops.model.Container.exists", new=Mock())
    @patch("ops.model.Container.exec", new_callable=Mock)
    @patch("ops.model.Container.push", new=Mock())
    def test_given_certifier_relation_not_created_when_on_pebble_ready_event_then_status_is_blocked(  # noqa: E501
        self, _
    ):
        self.harness.set_leader(True)

        self.harness.add_relation(
            relation_name="cert-admin-operator", remote_app="orc8r-certifier"
        )
        self.harness.add_relation(relation_name="metrics-endpoint", remote_app="prometheus-k8s")
        accessd_relation = self.harness.add_relation(
            relation_name="magma-orc8r-accessd", remote_app="orc8r-accessd"
        )
        self.harness.add_relation_unit(
            relation_id=accessd_relation, remote_unit_name="magma-orc8r-accessd/0"
        )
        self.harness.update_relation_data(
            relation_id=accessd_relation,
            app_or_unit="magma-orc8r-accessd/0",
            key_values={"active": "True"},
        )
        service_registry_relation = self.harness.add_relation(
            relation_name="magma-orc8r-service-registry", remote_app="orc8r-service-registry"
        )
        self.harness.add_relation_unit(
            relation_id=service_registry_relation,
            remote_unit_name="magma-orc8r-service-registry/0",
        )
        self.harness.update_relation_data(
            relation_id=service_registry_relation,
            app_or_unit="magma-orc8r-service-registry/0",
            key_values={"active": "True"},
        )

        self.harness.container_pebble_ready("magma-orc8r-orchestrator")

        assert self.harness.charm.unit.status == BlockedStatus(
            "Waiting for relation(s) to be created: magma-orc8r-certifier"
        )

    @patch("ops.model.Container.exists", new=Mock())
    @patch("ops.model.Container.exec", new_callable=Mock)
    @patch("ops.model.Container.push", new=Mock())
    def test_given_certifier_relation_not_ready_when_on_pebble_ready_event_then_status_is_waiting(
        self, patch_exec
    ):
        patch_exec.return_value = MockExec()
        self.harness.set_leader(True)

        self.harness.add_relation(
            relation_name="cert-admin-operator", remote_app="orc8r-certifier"
        )
        metricsd_relation = self.harness.add_relation(
            relation_name="metrics-endpoint", remote_app="prometheus-k8s"
        )
        self.harness.add_relation_unit(
            relation_id=metricsd_relation, remote_unit_name="prometheus-k8s/0"
        )
        self.harness.update_relation_data(
            relation_id=metricsd_relation,
            app_or_unit="prometheus-k8s/0",
            key_values={"active": "True"},
        )
        accessd_relation = self.harness.add_relation(
            relation_name="magma-orc8r-accessd", remote_app="orc8r-accessd"
        )
        self.harness.add_relation_unit(
            relation_id=accessd_relation, remote_unit_name="magma-orc8r-accessd/0"
        )
        self.harness.update_relation_data(
            relation_id=accessd_relation,
            app_or_unit="magma-orc8r-accessd/0",
            key_values={"active": "True"},
        )
        service_registry_relation = self.harness.add_relation(
            relation_name="magma-orc8r-service-registry", remote_app="orc8r-service-registry"
        )
        self.harness.add_relation_unit(
            relation_id=service_registry_relation,
            remote_unit_name="magma-orc8r-service-registry/0",
        )
        self.harness.update_relation_data(
            relation_id=service_registry_relation,
            app_or_unit="magma-orc8r-service-registry/0",
            key_values={"active": "True"},
        )
        certifier_relation = self.harness.add_relation(
            relation_name="magma-orc8r-certifier", remote_app="orc8r-certifier"
        )
        self.harness.add_relation_unit(
            relation_id=certifier_relation,
            remote_unit_name="magma-orc8r-certifier/0",
        )

        self.harness.container_pebble_ready("magma-orc8r-orchestrator")

        assert self.harness.charm.unit.status == WaitingStatus(
            "Waiting for relation(s) to be ready: magma-orc8r-certifier"
        )

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.exec", new_callable=Mock)
    @patch("ops.model.Container.push", new=Mock())
    def test_given_relations_ready_and_container_can_connect_and_unit_is_not_leader_when_on_pebble_ready_event_then_orchestrator_admin_user_is_not_created(  # noqa: E501
        self, patch_exec, patch_exists
    ):
        patch_exists.return_value = True
        patch_exec.return_value = MockExec()
        self.harness.set_leader(False)

        self.harness.add_relation(
            relation_name="cert-admin-operator", remote_app="orc8r-certifier"
        )
        self.harness.add_relation(relation_name="metrics-endpoint", remote_app="prometheus-k8s")
        accessd_relation = self.harness.add_relation(
            relation_name="magma-orc8r-accessd", remote_app="orc8r-accessd"
        )

        self.harness.add_relation_unit(
            relation_id=accessd_relation, remote_unit_name="magma-orc8r-accessd/0"
        )

        self.harness.update_relation_data(
            relation_id=accessd_relation,
            app_or_unit="magma-orc8r-accessd/0",
            key_values={"active": "True"},
        )
        self.harness.container_pebble_ready("magma-orc8r-orchestrator")

        patch_exec.assert_not_called()

    @patch("ops.model.Container.exec", new_callable=Mock)
    @patch("ops.model.Container.push")
    def test_given_relations_not_ready_when_pebble_ready_event_then_orchestrator_admin_user_is_not_created(  # noqa: E501
        self, patch_push, patch_exec
    ):
        patch_exec.return_value = MockExec()
        container = self.harness.model.unit.get_container("magma-orc8r-orchestrator")
        self.harness.charm.on.magma_orc8r_orchestrator_pebble_ready.emit(container)
        patch_exec.assert_not_called()

    @patch("ops.model.Container.exec", new_callable=Mock)
    @patch("ops.model.Container.push")
    def test_given_orchestrator_service_not_running_when_pebble_ready_event_then_orchestrator_admin_user_is_not_created(  # noqa: E501
        self, patch_push, patch_exec
    ):
        patch_exec.return_value = MockExec()
        self.harness.add_relation(
            relation_name="cert-admin-operator", remote_app="orc8r-certifier"
        )
        self.harness.add_relation(relation_name="metrics-endpoint", remote_app="prometheus-k8s")
        accessd_relation = self.harness.add_relation(
            relation_name="magma-orc8r-accessd", remote_app="orc8r-accessd"
        )

        self.harness.add_relation_unit(
            relation_id=accessd_relation, remote_unit_name="magma-orc8r-accessd/0"
        )

        self.harness.update_relation_data(
            relation_id=accessd_relation,
            app_or_unit="magma-orc8r-accessd/0",
            key_values={"active": "True"},
        )
        container = self.harness.model.unit.get_container("magma-orc8r-orchestrator")
        self.harness.set_can_connect(container, False)
        self.harness.charm.on.magma_orc8r_orchestrator_pebble_ready.emit(container)
        patch_exec.assert_not_called()

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
    def test_given_bad_elasticsearch_config_when_on_config_changed_event_then_status_is_blocked(
        self, _
    ):
        config = {"elasticsearch-url": "hello"}
        self.harness.container_pebble_ready("magma-orc8r-orchestrator")

        self.harness.update_config(key_values=config)

        assert self.harness.charm.unit.status == BlockedStatus(
            "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
        )

    @patch("ops.model.Container.get_service", new=Mock())
    def test_given_magma_orc8r_orchestrator_service_running_when_magma_orc8r_orchestrator_relation_joined_event_emitted_then_active_key_in_relation_data_is_set_to_true(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect("magma-orc8r-orchestrator", True)
        container = self.harness.model.unit.get_container("magma-orc8r-orchestrator")
        self.harness.container_pebble_ready(container_name="magma-orc8r-orchestrator")
        self.harness.set_leader(True)
        self.harness.set_can_connect(container=container, val=True)
        relation_id = self.harness.add_relation("magma-orc8r-orchestrator", "orc8r-orchestrator")

        self.harness.add_relation_unit(relation_id, "magma-orc8r-orchestrator/0")

        self.assertEqual(
            self.harness.get_relation_data(relation_id, "magma-orc8r-orchestrator/0"),
            {"active": "True"},
        )

    def test_given_magma_orc8r_orchestrator_service_not_running_when_magma_orc8r_orchestrator_relation_joined_event_emitted_then_active_key_in_relation_data_is_set_to_false(  # noqa: E501
        self,
    ):
        self.harness.set_leader(True)
        relation_id = self.harness.add_relation("magma-orc8r-orchestrator", "orc8r-orchestrator")
        self.harness.add_relation_unit(relation_id, "magma-orc8r-orchestrator/0")

        self.assertEqual(
            self.harness.get_relation_data(relation_id, "magma-orc8r-orchestrator/0"),
            {"active": "False"},
        )

    @patch("lightkube.Client.list")
    @patch("lightkube.core.client.GenericSyncClient")
    def test_given_k8s_services_exist_when_get_load_balancer_services_action_then_services_are_returned(  # noqa: E501
        self, _, patch_k8s_list
    ):
        event = Mock()
        ip_1 = "whatever ip 1"
        ip_2 = "whatever ip 2"
        ip_3 = "whatever ip 3"
        ip_4 = "whatever ip 4"
        name_1 = "whatever name 1"
        name_2 = "whatever name 2"
        name_3 = "whatever name 3"
        name_4 = "whatever name 4"
        service_1 = self.k8s_load_balancer_service(ip=ip_1, name=name_1)
        service_2 = self.k8s_load_balancer_service(ip=ip_2, name=name_2)
        service_3 = self.k8s_load_balancer_service(ip=ip_3, name=name_3)
        service_4 = self.k8s_load_balancer_service(ip=ip_4, name=name_4)
        patch_k8s_list.return_value = [service_1, service_2, service_3, service_4]

        self.harness.charm._on_get_load_balancer_services_action(event)

        event.set_results.assert_called_with(
            {
                name_1: ip_1,
                name_2: ip_2,
                name_3: ip_3,
                name_4: ip_4,
            }
        )

    def test_given_metrics_endpoint_relation_is_not_created_when_pebble_ready_then_status_is_blocked(  # noqa: E501
        self,
    ):
        self.harness.add_relation(
            relation_name="cert-admin-operator", remote_app="orc8r-certifier"
        )

        self.harness.add_relation(
            relation_name="magma-orc8r-certifier", remote_app="orc8r-certifier"
        )

        self.harness.add_relation(relation_name="magma-orc8r-accessd", remote_app="orc8r-accessd")
        self.harness.add_relation(
            relation_name="magma-orc8r-service-registry", remote_app="orc8r-service-registry"
        )

        self.harness.container_pebble_ready(container_name="magma-orc8r-orchestrator")

        self.assertEqual(
            BlockedStatus("Waiting for relation(s) to be created: metrics-endpoint"),
            self.harness.charm.unit.status,
        )

    @patch("ops.model.Container.exec", new_callable=Mock)
    @patch("ops.model.Container.exists", new=Mock())
    def test_given_pebble_ready_when_required_relation_broken_then_status_is_blocked(  # noqa: E501
        self, patch_exec
    ):
        patch_exec.return_value = MockExec()
        self.harness.add_relation(
            relation_name="cert-admin-operator", remote_app="orc8r-certifier"
        )
        self._create_relations()
        self.harness.container_pebble_ready("magma-orc8r-orchestrator")
        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())

        self.harness.charm.on.metrics_endpoint_relation_broken.emit(
            self.harness.model.get_relation("metrics-endpoint")
        )
        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for relation(s) to be created: metrics-endpoint"),
        )
        self.harness.charm.on.magma_orc8r_accessd_relation_broken.emit(
            self.harness.model.get_relation("magma-orc8r-accessd")
        )
        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for relation(s) to be created: magma-orc8r-accessd"),
        )
        self.harness.charm.on.magma_orc8r_service_registry_relation_broken.emit(
            self.harness.model.get_relation("magma-orc8r-service-registry")
        )
        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for relation(s) to be created: magma-orc8r-service-registry"),
        )

    def test_given_cert_admin_operator_relation_is_not_created_when_pebble_ready_then_status_is_blocked(  # noqa: E501
        self,
    ):
        self.harness.add_relation(relation_name="metrics-endpoint", remote_app="prometheus-k8s")
        self.harness.add_relation(
            relation_name="magma-orc8r-certifier", remote_app="orc8r-certifier"
        )

        accessd_relation = self.harness.add_relation(
            relation_name="magma-orc8r-accessd", remote_app="orc8r-accessd"
        )
        self.harness.add_relation(
            relation_name="magma-orc8r-service-registry", remote_app="orc8r-service-registry"
        )

        self.harness.add_relation_unit(
            relation_id=accessd_relation, remote_unit_name="magma-orc8r-accessd/0"
        )

        self.harness.update_relation_data(
            relation_id=accessd_relation,
            app_or_unit="magma-orc8r-accessd/0",
            key_values={"active": "True"},
        )

        self.harness.container_pebble_ready(container_name="magma-orc8r-orchestrator")

        self.assertEqual(
            BlockedStatus("Waiting for relation(s) to be created: cert-admin-operator"),
            self.harness.charm.unit.status,
        )

    @patch("ops.model.Container.push")
    def test_given_pebble_ready_when_certificate_available_then(self, patch_push):
        certificate = "whatever certificate"
        private_key = "whatever private key"
        event = Mock()
        event.certificate = certificate
        event.private_key = private_key

        container = self.harness.model.unit.get_container("magma-orc8r-orchestrator")
        self.harness.set_can_connect(container=container, val=True)

        self.harness.charm._on_certificate_available(event=event)

        patch_push.assert_has_calls(
            calls=[
                call(path="/var/opt/magma/certs/admin_operator.pem", source=certificate),
                call(path="/var/opt/magma/certs/admin_operator.key.pem", source=private_key),
            ]
        )

    def _create_relations(self):

        self.harness.add_relation(relation_name="metrics-endpoint", remote_app="prometheus-k8s")
        accessd_relation = self.harness.add_relation(
            relation_name="magma-orc8r-accessd", remote_app="orc8r-accessd"
        )
        self.harness.add_relation_unit(
            relation_id=accessd_relation, remote_unit_name="magma-orc8r-accessd/0"
        )
        self.harness.update_relation_data(
            relation_id=accessd_relation,
            app_or_unit="magma-orc8r-accessd/0",
            key_values={"active": "True"},
        )
        service_registry_relation = self.harness.add_relation(
            relation_name="magma-orc8r-service-registry", remote_app="orc8r-service-registry"
        )
        self.harness.add_relation_unit(
            relation_id=service_registry_relation,
            remote_unit_name="magma-orc8r-service-registry/0",
        )
        self.harness.update_relation_data(
            relation_id=service_registry_relation,
            app_or_unit="magma-orc8r-service-registry/0",
            key_values={"active": "True"},
        )
        certifier_relation = self.harness.add_relation(
            relation_name="magma-orc8r-certifier", remote_app="orc8r-certifier"
        )
        self.harness.add_relation_unit(
            relation_id=certifier_relation,
            remote_unit_name="magma-orc8r-certifier/0",
        )
        self.harness.update_relation_data(
            relation_id=certifier_relation,
            app_or_unit="magma-orc8r-certifier/0",
            key_values={"active": "True"},
        )
