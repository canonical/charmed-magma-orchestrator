# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, call, patch

from httpx import HTTPStatusError, Request, Response
from lightkube.models.core_v1 import ServicePort, ServiceSpec
from lightkube.models.meta_v1 import ObjectMeta
from lightkube.resources.core_v1 import Service
from ops import testing
from ops.model import BlockedStatus, WaitingStatus

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
    @patch("ops.model.Container.exec")
    def test_given_domain_config_set_when_install_then_nginx_config_file_is_created(
        self, patch_exec
    ):
        event = Mock()
        domain = "whatever domain"
        key_values = {"domain": domain}
        self.harness.update_config(key_values=key_values)
        container = self.harness.model.unit.get_container("magma-orc8r-nginx")
        self.harness.set_can_connect(container=container, val=True)

        self.harness.charm._on_install(event)

        patch_exec.assert_called_with(
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
    @patch("ops.model.Container.exec", new=Mock())
    def test_given_domain_config_set_when_install_then_additional_k8s_services_are_created(
        self, patch_create, patch_get
    ):
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

    @patch("ops.model.Container.exists")
    def test_given_all_relations_created_and_ready_and_nginx_services_are_created_when_pebble_ready_event_emitted_then_pebble_layer_is_configured(  # noqa: E501
        self, patch_file_exists
    ):
        patch_file_exists.return_value = True
        self.harness.update_config(key_values={"domain": "whatever.com"})
        bootstrapper_relation = self.harness.add_relation(
            relation_name="magma-orc8r-bootstrapper", remote_app="magma-orc8r-bootstrapper"
        )
        obsidian_relation = self.harness.add_relation(
            relation_name="magma-orc8r-obsidian", remote_app="magma-orc8r-obsidian"
        )
        self.harness.add_relation(
            relation_name="cert-certifier", remote_app="magma-orc8r-certifier"
        )
        self.harness.add_relation(
            relation_name="cert-controller", remote_app="magma-orc8r-certifier"
        )
        self.harness.add_relation_unit(
            relation_id=bootstrapper_relation, remote_unit_name="magma-orc8r-bootstrapper/0"
        )

        self.harness.update_relation_data(
            relation_id=bootstrapper_relation,
            app_or_unit="magma-orc8r-bootstrapper/0",
            key_values={"active": "True"},
        )
        self.harness.add_relation_unit(
            relation_id=obsidian_relation, remote_unit_name="magma-orc8r-obsidian/0"
        )
        self.harness.update_relation_data(
            relation_id=obsidian_relation,
            app_or_unit="magma-orc8r-obsidian/0",
            key_values={"active": "True"},
        )

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
    def test_given_magma_orc8r_obsidian_relation_not_ready_when_pebble_ready_event_emitted_then_status_is_blocked(  # noqa: E501
        self, patch_file_exists
    ):
        patch_file_exists.return_value = True
        self.harness.update_config(key_values={"domain": "whatever.com"})
        bootstrapper_relation = self.harness.add_relation(
            relation_name="magma-orc8r-bootstrapper", remote_app="magma-orc8r-bootstrapper"
        )
        self.harness.add_relation_unit(
            relation_id=bootstrapper_relation, remote_unit_name="orc8r-bootstrapper/0"
        )
        self.harness.update_relation_data(
            relation_id=bootstrapper_relation,
            app_or_unit="orc8r-bootstrapper/0",
            key_values={"active": "True"},
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
    def test_given_magma_orc8r_bootstrapper_relation_not_ready_when_pebble_ready_event_emitted_then_status_is_blocked(  # noqa: E501
        self, patch_file_exists
    ):
        patch_file_exists.return_value = True
        self.harness.update_config(key_values={"domain": "whatever.com"})
        obsidian_relation = self.harness.add_relation(
            relation_name="magma-orc8r-obsidian", remote_app="magma-orc8r-obsidian"
        )
        self.harness.add_relation_unit(
            relation_id=obsidian_relation, remote_unit_name="orc8r-obsidian/0"
        )
        self.harness.update_relation_data(
            relation_id=obsidian_relation,
            app_or_unit="orc8r-obsidian/0",
            key_values={"active": "True"},
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


class MockExec:
    def __init__(self, *args, **kwargs):
        pass

    def exec(self, *args, **kwargs):
        pass

    def wait_output(self, *args, **kwargs):
        return "test stdout", "test err"
