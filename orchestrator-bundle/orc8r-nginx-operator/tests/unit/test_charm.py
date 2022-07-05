# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, PropertyMock, call, patch

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
        self.harness = testing.Harness(MagmaOrc8rNginxCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_given_no_relations_created_when_pebble_ready_event_emitted_then_charm_goes_to_blocked_state(  # noqa: E501
        self,
    ):
        event = Mock()
        self.harness.charm.on.magma_orc8r_nginx_pebble_ready.emit(event)
        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus(
                "Waiting for relation(s) to be created: magma-orc8r-bootstrapper, magma-orc8r-certifier, magma-orc8r-obsidian"  # noqa: E501, W505
            ),
        )

    def test_given_certifier_relation_is_created_but_bootstrapper_and_obsidian_relations_are_missing_when_pebble_ready_event_emitted_then_charm_goes_to_blocked_state(  # noqa: E501
        self,
    ):
        event = Mock()
        relation_id = self.harness.add_relation("magma-orc8r-certifier", "magma-orc8r-certifier")
        self.harness.add_relation_unit(relation_id, "magma-orc8r-certifier/0")
        self.harness.charm.on.magma_orc8r_nginx_pebble_ready.emit(event)
        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus(
                "Waiting for relation(s) to be created: magma-orc8r-bootstrapper, magma-orc8r-obsidian"  # noqa: E501, W505
            ),
        )

    def test_given_bootstrapper_relation_is_created_but_certifier_and_obsidian_relations_are_missing_when_pebble_ready_event_emitted_then_charm_goes_to_blocked_state(  # noqa: E501
        self,
    ):
        event = Mock()
        relation_id = self.harness.add_relation(
            "magma-orc8r-bootstrapper", "magma-orc8r-bootstrapper"
        )
        self.harness.add_relation_unit(relation_id, "magma-orc8r-bootstrapper/0")
        self.harness.charm.on.magma_orc8r_nginx_pebble_ready.emit(event)
        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus(
                "Waiting for relation(s) to be created: magma-orc8r-certifier, magma-orc8r-obsidian"  # noqa: E501, W505
            ),
        )

    def test_given_all_relations_created_but_not_ready_when_pebble_ready_event_emitted_then_charm_goes_to_waiting_state(  # noqa: E501
        self,
    ):
        event = Mock()
        bootstrapper_relation_id = self.harness.add_relation(
            "magma-orc8r-bootstrapper", "magma-orc8r-bootstrapper"
        )
        self.harness.add_relation_unit(bootstrapper_relation_id, "magma-orc8r-bootstrapper/0")
        certifier_relation_id = self.harness.add_relation(
            "magma-orc8r-certifier", "magma-orc8r-certifier"
        )
        self.harness.add_relation_unit(certifier_relation_id, "magma-orc8r-certifier/0")
        obsidian_relation_id = self.harness.add_relation(
            "magma-orc8r-obsidian", "magma-orc8r-obsidian"
        )
        self.harness.add_relation_unit(obsidian_relation_id, "magma-orc8r-obsidian/0")
        self.harness.charm.on.magma_orc8r_nginx_pebble_ready.emit(event)
        self.assertEqual(
            self.harness.charm.unit.status,
            WaitingStatus(
                "Waiting for relation(s) to be ready: magma-orc8r-bootstrapper, magma-orc8r-certifier, magma-orc8r-obsidian"  # noqa: E501, W505
            ),
        )

    def test_given_all_relations_created_and_bootstrapper_relation_ready_but_certifier_and_obsidian_relations_not_ready_when_pebble_ready_event_emitted_then_charm_goes_to_waiting_state(  # noqa: E501
        self,
    ):
        event = Mock()
        bootstrapper_relation_id = self.harness.add_relation(
            "magma-orc8r-bootstrapper", "magma-orc8r-bootstrapper"
        )
        self.harness.add_relation_unit(bootstrapper_relation_id, "magma-orc8r-bootstrapper/0")
        certifier_relation_id = self.harness.add_relation(
            "magma-orc8r-certifier", "magma-orc8r-certifier"
        )
        self.harness.add_relation_unit(certifier_relation_id, "magma-orc8r-certifier/0")
        obsidian_relation_id = self.harness.add_relation(
            "magma-orc8r-obsidian", "magma-orc8r-obsidian"
        )
        self.harness.add_relation_unit(obsidian_relation_id, "magma-orc8r-obsidian/0")
        self.harness.update_relation_data(
            bootstrapper_relation_id, "magma-orc8r-bootstrapper/0", {"active": "True"}
        )
        self.harness.charm.on.magma_orc8r_nginx_pebble_ready.emit(event)
        self.assertEqual(
            self.harness.charm.unit.status,
            WaitingStatus(
                "Waiting for relation(s) to be ready: magma-orc8r-certifier, magma-orc8r-obsidian"
            ),
        )

    @patch("charm.MagmaOrc8rNginxCharm._on_magma_orc8r_certifier_relation_changed", Mock())
    def test_given_all_relations_created_and_certifier_relation_ready_but_bootstrapper_and_obsidian_relations_not_ready_when_pebble_ready_event_emitted_then_charm_goes_to_waiting_state(  # noqa: E501
        self,
    ):
        event = Mock()
        bootstrapper_relation_id = self.harness.add_relation(
            "magma-orc8r-bootstrapper", "magma-orc8r-bootstrapper"
        )
        self.harness.add_relation_unit(bootstrapper_relation_id, "magma-orc8r-bootstrapper/0")
        certifier_relation_id = self.harness.add_relation(
            "magma-orc8r-certifier", "magma-orc8r-certifier"
        )
        self.harness.add_relation_unit(certifier_relation_id, "magma-orc8r-certifier/0")
        obsidian_relation_id = self.harness.add_relation(
            "magma-orc8r-obsidian", "magma-orc8r-obsidian"
        )
        self.harness.add_relation_unit(obsidian_relation_id, "magma-orc8r-obsidian/0")
        self.harness.update_relation_data(
            certifier_relation_id, "magma-orc8r-certifier/0", {"active": "True"}
        )
        self.harness.charm.on.magma_orc8r_nginx_pebble_ready.emit(event)
        self.assertEqual(
            self.harness.charm.unit.status,
            WaitingStatus(
                "Waiting for relation(s) to be ready: magma-orc8r-bootstrapper, magma-orc8r-obsidian"  # noqa: E501, W505
            ),
        )

    def test_given_all_relations_created_and_obsidian_relation_ready_but_bootstrapper_and_certifier_relations_not_ready_when_pebble_ready_event_emitted_then_charm_goes_to_waiting_state(  # noqa: E501
        self,
    ):
        event = Mock()
        bootstrapper_relation_id = self.harness.add_relation(
            "magma-orc8r-bootstrapper", "magma-orc8r-bootstrapper"
        )
        self.harness.add_relation_unit(bootstrapper_relation_id, "magma-orc8r-bootstrapper/0")
        certifier_relation_id = self.harness.add_relation(
            "magma-orc8r-certifier", "magma-orc8r-certifier"
        )
        self.harness.add_relation_unit(certifier_relation_id, "magma-orc8r-certifier/0")
        obsidian_relation_id = self.harness.add_relation(
            "magma-orc8r-obsidian", "magma-orc8r-obsidian"
        )
        self.harness.add_relation_unit(obsidian_relation_id, "magma-orc8r-obsidian/0")
        self.harness.update_relation_data(
            obsidian_relation_id, "magma-orc8r-obsidian/0", {"active": "True"}
        )
        self.harness.charm.on.magma_orc8r_nginx_pebble_ready.emit(event)
        self.assertEqual(
            self.harness.charm.unit.status,
            WaitingStatus(
                "Waiting for relation(s) to be ready: magma-orc8r-bootstrapper, magma-orc8r-certifier"  # noqa: E501, W505
            ),
        )

    @patch("lightkube.core.client.Client.create")
    @patch("lightkube.core.client.Client.get")
    @patch("lightkube.core.client.GenericSyncClient", Mock())
    @patch("charm.MagmaOrc8rNginxCharm._namespace", new_callable=PropertyMock)
    @patch("charm.MagmaOrc8rNginxCharm._relations_created", PropertyMock(return_value=True))
    @patch("charm.MagmaOrc8rNginxCharm._relations_ready", PropertyMock(return_value=True))
    @patch("charm.MagmaOrc8rNginxCharm._get_domain_name", PropertyMock(return_value=True))
    def test_given_all_relations_created_and_ready_and_nginx_services_not_created_when_pebble_ready_event_emitted_then_nginx_services_are_created(  # noqa: E501
        self, patch_namespace, patch_get, patch_create
    ):
        namespace = "test"
        patch_namespace.return_value = namespace
        event = Mock()
        patch_get.side_effect = HTTPStatusError(
            message="whatever message",
            request=Request(method="whatever method", url="whatever url"),
            response=Response(status_code=400),
        )

        expected_calls = [
            call(
                Service(
                    apiVersion="v1",
                    kind="Service",
                    metadata=ObjectMeta(
                        namespace=namespace,
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
            call(
                Service(
                    apiVersion="v1",
                    kind="Service",
                    metadata=ObjectMeta(
                        namespace=namespace,
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
                                nodePort=31200,
                            ),
                            ServicePort(
                                name="open-legacy",
                                port=443,
                                targetPort=8444,
                                nodePort=30747,
                            ),
                            ServicePort(
                                name="open",
                                port=8444,
                                targetPort=8444,
                                nodePort=30618,
                            ),
                        ],
                        type="LoadBalancer",
                    ),
                )
            ),
        ]

        self.harness.charm.on.magma_orc8r_nginx_pebble_ready.emit(event)

        patch_create.assert_has_calls(expected_calls, any_order=True)

    @patch("ops.model.Container.exec", new_callable=Mock)
    @patch("lightkube.core.client.Client.get")
    @patch("lightkube.core.client.GenericSyncClient", Mock())
    @patch("charm.MagmaOrc8rNginxCharm._namespace", new_callable=PropertyMock)
    @patch("charm.MagmaOrc8rNginxCharm._relations_created", PropertyMock(return_value=True))
    @patch("charm.MagmaOrc8rNginxCharm._relations_ready", PropertyMock(return_value=True))
    @patch("charm.MagmaOrc8rNginxCharm._get_domain_name", PropertyMock(return_value=True))
    def test_given_all_relations_created_and_ready_and_nginx_services_are_created_when_pebble_ready_event_emitted_then_nginx_config_file_is_created(  # noqa: E501
        self, patch_namespace, patch_get, patch_exec
    ):
        patch_exec.return_value = MockExec()
        namespace = "test"
        patch_namespace.return_value = namespace
        event = Mock()
        patch_get.return_value = Service(
            kind="Service",
            metadata=ObjectMeta(
                name="some service",
                namespace="whatever",
            ),
        )
        self.harness.set_can_connect("magma-orc8r-nginx", True)

        self.harness.charm.on.magma_orc8r_nginx_pebble_ready.emit(event)

        patch_exec.assert_called_with(
            command=["/usr/local/bin/generate_nginx_configs.py"],
            environment={
                "PROXY_BACKENDS": "test.svc.cluster.local",
                "CONTROLLER_HOSTNAME": "controller.True",
                "RESOLVER": "kube-dns.kube-system.svc.cluster.local valid=10s",
                "SERVICE_REGISTRY_MODE": "k8s",
            },
        )

    @patch("lightkube.core.client.Client.get")
    @patch("lightkube.core.client.GenericSyncClient", Mock())
    @patch("charm.MagmaOrc8rNginxCharm._namespace", new_callable=PropertyMock)
    @patch("charm.MagmaOrc8rNginxCharm._generate_nginx_config", Mock())
    @patch("charm.MagmaOrc8rNginxCharm._relations_created", PropertyMock(return_value=True))
    @patch("charm.MagmaOrc8rNginxCharm._relations_ready", PropertyMock(return_value=True))
    @patch("charm.MagmaOrc8rNginxCharm._get_domain_name", PropertyMock(return_value=True))
    def test_given_all_relations_created_and_ready_and_nginx_services_are_created_when_pebble_ready_event_emitted_then_pebble_layer_is_configured(  # noqa: E501
        self, patch_namespace, patch_get
    ):
        namespace = "test"
        patch_namespace.return_value = namespace
        event = Mock()
        patch_get.return_value = Service(
            kind="Service",
            metadata=ObjectMeta(
                name="some service",
                namespace="whatever",
            ),
        )
        expected_plan = {
            "services": {
                "magma-orc8r-nginx": {
                    "override": "replace",
                    "startup": "enabled",
                    "command": "nginx",
                    "environment": {
                        "SERVICE_REGISTRY_MODE": "k8s",
                        "SERVICE_REGISTRY_NAMESPACE": namespace,
                    },
                }
            },
        }
        self.harness.set_can_connect("magma-orc8r-nginx", True)

        self.harness.charm.on.magma_orc8r_nginx_pebble_ready.emit(event)

        updated_plan = self.harness.get_container_pebble_plan("magma-orc8r-nginx").to_dict()
        self.assertEqual(expected_plan, updated_plan)


class MockExec:
    def __init__(self, *args, **kwargs):
        pass

    def exec(self, *args, **kwargs):
        pass

    def wait_output(self, *args, **kwargs):
        return "test stdout", "test err"
