# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, call, patch

from httpx import HTTPStatusError, Request, Response
from lightkube.models.core_v1 import ServicePort, ServiceSpec
from lightkube.models.meta_v1 import ObjectMeta
from lightkube.resources.core_v1 import Service
from ops import testing
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

from charm import MagmaOrc8rNginxCharm

testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports, service_type, service_name, additional_labels, additional_selectors: None,  # noqa: E501
    )
    def setUp(self):
        self.namespace = "whatever"
        self.harness = testing.Harness(MagmaOrc8rNginxCharm)
        self.harness.set_model_name(name=self.namespace)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch("lightkube.core.client.GenericSyncClient", new=Mock())
    @patch("lightkube.core.client.Client.create", new=Mock())
    @patch("ops.model.Container.exec", new_callable=Mock)
    def test_given_domain_config_set_when_install_then_nginx_config_file_is_created(
        self, patched_exec
    ):
        patched_exec.return_value = MockExec()
        event = Mock()
        domain = "whatever domain"
        key_values = {"domain": domain}
        self.harness.update_config(key_values=key_values)
        container = self.harness.model.unit.get_container("magma-orc8r-nginx")
        self.harness.set_can_connect(container=container, val=True)

        self.harness.charm._on_install(event)

        patched_exec.assert_called_with(
            command=["/usr/local/bin/generate_nginx_configs.py"],
            environment={
                "PROXY_BACKENDS": f"{self.namespace}.svc.cluster.local",
                "CONTROLLER_HOSTNAME": f"controller.{domain}",
                "RESOLVER": "kube-dns.kube-system.svc.cluster.local valid=10s",
                "SERVICE_REGISTRY_MODE": "k8s",
            },
        )

    @patch("lightkube.core.client.GenericSyncClient", new=Mock())
    @patch("lightkube.core.client.Client.get")
    @patch("lightkube.core.client.Client.create")
    @patch("ops.model.Container.exec", new_callable=Mock)
    def test_given_domain_config_set_when_install_then_additional_k8s_services_are_created(
        self, patched_exec, patch_create, patch_get
    ):
        patched_exec.return_value = MockExec()
        patch_get.side_effect = HTTPStatusError(
            message="whatever",
            response=Response(status_code=400),
            request=Request(url="whatever", method="get"),
        )
        event = Mock()
        container = self.harness.model.unit.get_container("magma-orc8r-nginx")
        self.harness.set_can_connect(container=container, val=True)

        self.harness.charm._on_install(event)

        calls = [
            call(
                Service(
                    apiVersion="v1",
                    kind="Service",
                    metadata=ObjectMeta(
                        namespace=self.namespace,
                        name="orc8r-bootstrap-nginx",
                        labels={
                            "app.kubernetes.io/component": "nginx-proxy",
                            "app.kubernetes.io/part-of": "orc8r",
                        },
                    ),
                    spec=ServiceSpec(
                        selector={
                            "app.kubernetes.io/name": "orc8r-nginx",
                        },
                        ports=[
                            ServicePort(
                                name="health",
                                port=80,
                                targetPort=80,
                            ),
                            ServicePort(
                                name="open-legacy",
                                port=443,
                                targetPort=8444,
                            ),
                            ServicePort(
                                name="open",
                                port=8444,
                                targetPort=8444,
                            ),
                        ],
                        type="LoadBalancer",
                    ),
                )
            ),
            call(
                Service(
                    apiVersion="v1",
                    kind="Service",
                    metadata=ObjectMeta(
                        namespace=self.namespace,
                        name="orc8r-clientcert-nginx",
                        labels={
                            "app.kubernetes.io/component": "nginx-proxy",
                            "app.kubernetes.io/part-of": "orc8r",
                        },
                    ),
                    spec=ServiceSpec(
                        selector={"app.kubernetes.io/name": "orc8r-nginx"},
                        ports=[
                            ServicePort(
                                name="health",
                                port=80,
                                targetPort=80,
                            ),
                            ServicePort(
                                name="clientcert-legacy",
                                port=443,
                                targetPort=8443,
                            ),
                            ServicePort(
                                name="clientcert",
                                port=8443,
                                targetPort=8443,
                            ),
                        ],
                        type="LoadBalancer",
                    ),
                )
            ),
        ]

        patch_create.assert_has_calls(calls=calls)

    @patch("ops.model.Container.exec", Mock())
    def test_given_no_relations_created_when_pebble_ready_event_emitted_then_status_is_blocked(
        self,
    ):
        self.harness.update_config(key_values={"domain": "whatever.com"})

        self.harness.container_pebble_ready(container_name="magma-orc8r-nginx")

        self.assertEqual(
            BlockedStatus(
                "Waiting for relation(s) to be created: cert-certifier, cert-controller, "
                "magma-orc8r-bootstrapper, magma-orc8r-obsidian"
            ),
            self.harness.charm.unit.status,
        )

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.exec", Mock())
    def test_given_cert_certifier_relation_not_created_when_pebble_ready_event_emitted_then_status_is_blocked(  # noqa: E501
        self, patch_file_exists
    ):
        patch_file_exists.return_value = True
        self.harness.update_config(key_values={"domain": "whatever.com"})
        self.harness.add_relation(
            relation_name="magma-orc8r-bootstrapper", remote_app="magma-orc8r-bootstrapper"
        )
        self.harness.add_relation(
            relation_name="magma-orc8r-obsidian", remote_app="magma-orc8r-obsidian"
        )
        self.harness.add_relation(
            relation_name="cert-controller", remote_app="magma-orc8r-certifier"
        )

        self.harness.container_pebble_ready(container_name="magma-orc8r-nginx")

        self.assertEqual(
            BlockedStatus("Waiting for relation(s) to be created: cert-certifier"),
            self.harness.charm.unit.status,
        )

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.exec", Mock())
    def test_given_cert_controller_relation_not_created_when_pebble_ready_event_emitted_then_status_is_blocked(  # noqa: E501
        self, patch_file_exists
    ):
        patch_file_exists.return_value = True
        self.harness.update_config(key_values={"domain": "whatever.com"})
        self.harness.add_relation(
            relation_name="magma-orc8r-bootstrapper", remote_app="magma-orc8r-bootstrapper"
        )
        self.harness.add_relation(
            relation_name="magma-orc8r-obsidian", remote_app="magma-orc8r-obsidian"
        )
        self.harness.add_relation(
            relation_name="cert-certifier", remote_app="magma-orc8r-certifier"
        )

        self.harness.container_pebble_ready(container_name="magma-orc8r-nginx")

        self.assertEqual(
            BlockedStatus("Waiting for relation(s) to be created: cert-controller"),
            self.harness.charm.unit.status,
        )

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.exec", Mock())
    def test_given_magma_orc8r_bootstrapper_relation_not_created_when_pebble_ready_event_emitted_then_status_is_blocked(  # noqa: E501
        self, patch_file_exists
    ):
        patch_file_exists.return_value = True
        self.harness.update_config(key_values={"domain": "whatever.com"})
        self.harness.add_relation(
            relation_name="magma-orc8r-obsidian", remote_app="magma-orc8r-obsidian"
        )
        self.harness.add_relation(
            relation_name="cert-certifier", remote_app="magma-orc8r-certifier"
        )
        self.harness.add_relation(
            relation_name="cert-controller", remote_app="magma-orc8r-certifier"
        )

        self.harness.container_pebble_ready(container_name="magma-orc8r-nginx")

        self.assertEqual(
            BlockedStatus("Waiting for relation(s) to be created: magma-orc8r-bootstrapper"),
            self.harness.charm.unit.status,
        )

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.exec", Mock())
    def test_given_magma_orc8r_obsidian_relation_not_created_when_pebble_ready_event_emitted_then_status_is_blocked(  # noqa: E501
        self, patch_file_exists
    ):
        patch_file_exists.return_value = True
        self.harness.update_config(key_values={"domain": "whatever.com"})
        self.harness.add_relation(
            relation_name="magma-orc8r-bootstrapper", remote_app="magma-orc8r-bootstrapper"
        )
        self.harness.add_relation(
            relation_name="cert-certifier", remote_app="magma-orc8r-certifier"
        )
        self.harness.add_relation(
            relation_name="cert-controller", remote_app="magma-orc8r-certifier"
        )

        self.harness.container_pebble_ready(container_name="magma-orc8r-nginx")

        self.assertEqual(
            BlockedStatus("Waiting for relation(s) to be created: magma-orc8r-obsidian"),
            self.harness.charm.unit.status,
        )

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.exec", new_callable=Mock)
    def test_given_pebble_ready_when_obsidian_relation_broken_then_status_is_blocked(  # noqa: E501
        self, patched_exec, patch_file_exists
    ):
        patched_exec.return_value = MockExec()
        patch_file_exists.return_value = True
        self.harness.update_config(key_values={"domain": "whatever.com"})
        self._create_all_relations()
        self.harness.container_pebble_ready(container_name="magma-orc8r-nginx")

        self.harness.remove_relation(
            self.harness.model.get_relation("magma-orc8r-obsidian").id  # type: ignore[union-attr]
        )

        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for relation(s) to be created: magma-orc8r-obsidian"),
        )

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.exec", new_callable=Mock)
    def test_given_pebble_ready_when_bootstrapper_relation_broken_then_status_is_blocked(  # noqa: E501
        self, patched_exec, patch_file_exists
    ):
        patched_exec.return_value = MockExec()
        patch_file_exists.return_value = True
        self.harness.update_config(key_values={"domain": "whatever.com"})
        self._create_all_relations()
        self.harness.container_pebble_ready(container_name="magma-orc8r-nginx")
        self.harness.remove_relation(
            self.harness.model.get_relation(
                "magma-orc8r-bootstrapper"
            ).id  # type: ignore[union-attr]
        )
        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for relation(s) to be created: magma-orc8r-bootstrapper"),
        )

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.exec", Mock())
    def test_given_magma_orc8r_obsidian_relation_not_ready_when_pebble_ready_event_emitted_then_status_is_waiting(  # noqa: E501
        self, patch_file_exists
    ):
        patch_file_exists.return_value = True
        self.harness.update_config(key_values={"domain": "whatever.com"})
        self._create_active_relation(
            relation_name="magma-orc8r-bootstrapper", remote_app="magma-orc8r-bootstrapper"
        )

        self.harness.add_relation(
            relation_name="magma-orc8r-obsidian", remote_app="magma-orc8r-obsidian"
        )
        self.harness.add_relation(
            relation_name="cert-certifier", remote_app="magma-orc8r-certifier"
        )
        self.harness.add_relation(
            relation_name="cert-controller", remote_app="magma-orc8r-certifier"
        )

        self.harness.container_pebble_ready(container_name="magma-orc8r-nginx")

        self.assertEqual(
            WaitingStatus("Waiting for relation(s) to be ready: magma-orc8r-obsidian"),
            self.harness.charm.unit.status,
        )

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.exec", Mock())
    def test_given_magma_orc8r_bootstrapper_relation_not_ready_when_pebble_ready_event_emitted_then_status_is_waiting(  # noqa: E501
        self, patch_file_exists
    ):
        patch_file_exists.return_value = True
        self.harness.update_config(key_values={"domain": "whatever.com"})
        self._create_active_relation(
            relation_name="magma-orc8r-obsidian", remote_app="magma-orc8r-obsidian"
        )

        self.harness.add_relation(
            relation_name="magma-orc8r-bootstrapper", remote_app="magma-orc8r-bootstrapper"
        )
        self.harness.add_relation(
            relation_name="cert-certifier", remote_app="magma-orc8r-certifier"
        )
        self.harness.add_relation(
            relation_name="cert-controller", remote_app="magma-orc8r-certifier"
        )

        self.harness.container_pebble_ready(container_name="magma-orc8r-nginx")

        self.assertEqual(
            WaitingStatus("Waiting for relation(s) to be ready: magma-orc8r-bootstrapper"),
            self.harness.charm.unit.status,
        )

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.exec", new_callable=Mock)
    def test_given_all_relations_created_and_ready_and_nginx_services_are_created_when_pebble_ready_event_emitted_then_pebble_layer_is_configured(  # noqa: E501
        self, patched_exec, patch_file_exists
    ):
        patched_exec.return_value = MockExec()
        patch_file_exists.return_value = True
        self.harness.update_config(key_values={"domain": "whatever.com"})
        self._create_all_relations()
        expected_plan = {
            "services": {
                "magma-orc8r-nginx": {
                    "override": "replace",
                    "startup": "enabled",
                    "command": "nginx",
                    "environment": {
                        "SERVICE_REGISTRY_MODE": "k8s",
                        "SERVICE_REGISTRY_NAMESPACE": self.namespace,
                    },
                }
            },
        }

        self.harness.container_pebble_ready(container_name="magma-orc8r-nginx")

        updated_plan = self.harness.get_container_pebble_plan("magma-orc8r-nginx").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.exec", new_callable=Mock)
    def test_given_all_relations_created_and_ready_and_nginx_services_are_created_when_pebble_ready_event_emitted_then_status_is_active(  # noqa: E501
        self, patched_exec, patch_file_exists
    ):
        patched_exec.return_value = MockExec()
        patch_file_exists.return_value = True
        self.harness.update_config(key_values={"domain": "whatever.com"})
        self._create_all_relations()
        self.harness.container_pebble_ready(container_name="magma-orc8r-nginx")

        self.assertEqual(ActiveStatus(), self.harness.charm.unit.status)

    def test_given_orc8r_nginx_service_not_running_when_orc8r_nginx_relation_joined_then_service_active_status_in_the_relation_data_bag_is_false(  # noqa: E501
        self,
    ):
        self.harness.set_leader(True)
        relation_id = self.harness.add_relation("magma-orc8r-nginx", "orc8r-nginx")
        self.harness.add_relation_unit(relation_id, "magma-orc8r-nginx/0")

        self.assertEqual(
            self.harness.get_relation_data(relation_id, "magma-orc8r-nginx/0"),
            {"active": "False"},
        )

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.exec", new_callable=Mock)
    @patch("ops.model.Container.push", Mock())
    @patch("ops.model.Container.exec", Mock())
    def test_given_metricsd_service_running_when_metricsd_relation_joined_then_service_active_status_in_the_relation_data_bag_is_true(  # noqa: E501
        self, patched_exec, patch_file_exists
    ):
        patched_exec.return_value = MockExec()
        self.harness.set_leader(True)
        patch_file_exists.return_value = True
        self.harness.update_config(key_values={"domain": "whatever.com"})
        self._create_all_relations()

        self.harness.container_pebble_ready(container_name="magma-orc8r-nginx")

        relation_id = self.harness.add_relation("magma-orc8r-nginx", "orc8r-nginx")
        self.harness.add_relation_unit(relation_id, "magma-orc8r-nginx/0")

        self.assertEqual(
            self.harness.get_relation_data(relation_id, "magma-orc8r-nginx/0"),
            {"active": "True"},
        )

    @patch("ops.model.Container.push")
    def test_given_container_can_be_connected_when_certifier_certificate_available_then_certifier_pem_is_pushed_to_workload(  # noqa: E501
        self, patched_push
    ):
        test_certifier_cert = "some cert"
        container = self.harness.model.unit.get_container("magma-orc8r-nginx")
        relation_id = self.harness.add_relation("cert-certifier", "whatever")
        self.harness.add_relation_unit(relation_id, "whatever/0")

        self.harness.set_can_connect(container=container, val=True)
        self.harness.update_relation_data(
            relation_id,
            "whatever/0",
            {"certificate": test_certifier_cert},
        )

        patched_push.assert_called_once_with(
            path="/var/opt/magma/certs/certifier.pem", source=test_certifier_cert
        )

    @patch("ops.model.Container.push")
    def test_given_container_can_be_connected_when_controller_certificate_available_then_controller_crt_and_controller_key_are_pushed_to_workload(  # noqa: E501
        self, patched_push
    ):
        test_controller_cert = "some cert"
        test_controller_key = "some key"
        container = self.harness.model.unit.get_container("magma-orc8r-nginx")
        relation_id = self.harness.add_relation("cert-controller", "whatever")
        self.harness.add_relation_unit(relation_id, "whatever/0")

        self.harness.set_can_connect(container=container, val=True)
        self.harness.update_relation_data(
            relation_id,
            "whatever/0",
            {"certificate": test_controller_cert, "private_key": test_controller_key},
        )

        patched_push.assert_has_calls(
            [
                call(path="/var/opt/magma/certs/controller.crt", source=test_controller_cert),
                call(path="/var/opt/magma/certs/controller.key", source=test_controller_key),
            ]
        )

    @patch("ops.model.Container.push")
    def test_given_container_can_be_connected_when_rootca_certificate_available_then_rootca_pem_is_pushed_to_workload(  # noqa: E501
        self, patched_push
    ):
        test_rootca_cert = "some cert"
        container = self.harness.model.unit.get_container("magma-orc8r-nginx")
        relation_id = self.harness.add_relation("cert-root-ca", "whatever")
        self.harness.add_relation_unit(relation_id, "whatever/0")

        self.harness.set_can_connect(container=container, val=True)
        self.harness.update_relation_data(
            relation_id,
            "whatever/0",
            {"certificate": test_rootca_cert},
        )

        patched_push.assert_called_once_with(
            path="/var/opt/magma/certs/rootCA.pem", source=test_rootca_cert
        )

    @patch("ops.model.Container.exec")
    def test_given_valid_domain_config_set_when_config_changed_then_nginx_config_file_is_recreated(
        self, patch_exec
    ):
        container = self.harness.model.unit.get_container("magma-orc8r-nginx")
        self.harness.set_can_connect(container=container, val=True)

        domain = "whateverdomain.com"
        key_values = {"domain": domain}
        self.harness.update_config(key_values=key_values)

        patch_exec.assert_called_with(
            command=["/usr/local/bin/generate_nginx_configs.py"],
            environment={
                "PROXY_BACKENDS": f"{self.namespace}.svc.cluster.local",
                "CONTROLLER_HOSTNAME": f"controller.{domain}",
                "RESOLVER": "kube-dns.kube-system.svc.cluster.local valid=10s",
                "SERVICE_REGISTRY_MODE": "k8s",
            },
        )

    def _create_active_relation(self, relation_name: str, remote_app: str):
        """Creates a relation between orc8r-nginx and a remote app.

         Mocks service status of remote app workload.

        Args:
            relation_name (str): Relation name
            remote_app (str): Remote application
        """
        relation_id = self.harness.add_relation(relation_name=relation_name, remote_app=remote_app)
        self.harness.add_relation_unit(relation_id=relation_id, remote_unit_name=f"{remote_app}/0")
        self.harness.update_relation_data(
            relation_id=relation_id,
            app_or_unit=f"{remote_app}/0",
            key_values={"active": "True"},
        )

    def _create_all_relations(self):
        self._create_active_relation(
            relation_name="magma-orc8r-bootstrapper", remote_app="magma-orc8r-bootstrapper"
        )
        self._create_active_relation(
            relation_name="magma-orc8r-obsidian", remote_app="magma-orc8r-obsidian"
        )
        self.harness.add_relation(
            relation_name="cert-certifier", remote_app="magma-orc8r-certifier"
        )
        self.harness.add_relation(
            relation_name="cert-controller", remote_app="magma-orc8r-certifier"
        )


class MockExec:
    def __init__(self, *args, **kwargs):
        pass

    def exec(self, *args, **kwargs):
        pass

    def wait_output(self, *args, **kwargs):
        return "test stdout", "test err"
