# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, call, patch

from ops import testing
from ops.model import BlockedStatus

from charm import MagmaOrc8rNginxCharm

testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports, service_type, service_name, additional_labels, additional_selectors: None,  # noqa: E501
    )
    def setUp(self):
        self.model_name = "whatever model name"
        self.container_name = self.service_name = "magma-orc8r-nginx"
        self.harness = testing.Harness(MagmaOrc8rNginxCharm)
        self.harness.set_model_name(self.model_name)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_given_bootstrapper_and_obsidian_relations_are_missing_when_pebble_ready_then_status_is_blocked(  # noqa: E501
        self,
    ):
        self.harness.container_pebble_ready(container_name=self.container_name)

        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for relations: bootstrapper, obsidian, certificates"),
        )

    @patch("lightkube.core.client.GenericSyncClient")
    @patch("ops.model.Container.exec")
    def test_given_domain_name_is_set_correctly_when_on_install_then_additional_orc8r_nginx_services_are_created(  # noqa: E501
        self, patch_exec, patch_client
    ):
        event = Mock()
        domain = "whatever domain"
        key_values = {"domain": domain}
        self.harness.update_config(key_values=key_values)

        self.harness.charm._on_install(event=event)

        patch_exec.assert_called_with(
            command=["/usr/local/bin/generate_nginx_configs.py"],
            environment={
                "PROXY_BACKENDS": f"{self.model_name}.svc.cluster.local",
                "CONTROLLER_HOSTNAME": f"controller.{domain}",
                "RESOLVER": "kube-dns.kube-system.svc.cluster.local valid=10s",
                "SERVICE_REGISTRY_MODE": "k8s",
            },
        )

    @patch("ops.model.Container.exists")
    def test_given_relations_established_and_domain_config_is_valid_when_pebble_ready_then_pebble_layer_is_configured(  # noqa: E501
        self, patch_exists
    ):
        patch_exists.return_value = True
        key_values = {"domain": "whatever.com"}
        self.harness.update_config(key_values=key_values)
        bootstrapper_relation_id = self.harness.add_relation(
            "bootstrapper", "magma-orc8r-bootstrapper"
        )
        obsidian_relation_id = self.harness.add_relation("obsidian", "magma-orc8r-obsidian")
        certificates_relation_id = self.harness.add_relation("certificates", "vault-k8s")
        self.harness.add_relation_unit(bootstrapper_relation_id, "magma-orc8r-bootstrapper/0")
        self.harness.add_relation_unit(obsidian_relation_id, "magma-orc8r-obsidian/0")
        self.harness.add_relation_unit(certificates_relation_id, "vault-k8s/0")

        self.harness.container_pebble_ready(container_name=self.container_name)

        expected_pebble_plan = {
            "services": {
                self.service_name: {
                    "startup": "enabled",
                    "override": "replace",
                    "command": "nginx",
                    "environment": {
                        "SERVICE_REGISTRY_MODE": "k8s",
                        "SERVICE_REGISTRY_NAMESPACE": self.model_name,
                    },
                }
            }
        }
        pebble_plan = self.harness.get_container_pebble_plan(
            container_name=self.container_name
        ).to_dict()
        self.assertEqual(expected_pebble_plan, pebble_plan)

    @patch("ops.model.Container.push")
    def test_given_pebble_ready_when_certificate_available_then_certs_are_pushed_to_container(
        self, patch_push
    ):
        event = Mock()
        domain_name = "whatever domain name"
        certificate = "whatever certificate"
        private_key = "whatever private key"
        key_values = {"domain": domain_name}
        event.certificate_data = {
            "common_name": f"*.{domain_name}",
            "cert": certificate,
            "key": private_key,
        }
        self.harness.update_config(key_values=key_values)

        self.harness.container_pebble_ready(container_name=self.container_name)

        self.harness.charm._on_certificate_available(event=event)

        calls = [
            call(path="/var/opt/magma/certs/controller.crt", source=certificate),
            call(path="/var/opt/magma/certs/controller.key", source=private_key),
        ]
        patch_push.assert_has_calls(calls=calls)

    @patch(
        "charms.tls_certificates_interface.v0.tls_certificates.InsecureCertificatesRequires.request_certificate"  # noqa: E501, W505
    )
    def test_given_correct_domain_config_when_on_certificates_relation_joined_then_certificate_requests_are_made(  # noqa: E501
        self, patch_request_certificate
    ):
        event = Mock()
        domain = "whatever domain"
        key_values = {"domain": domain}
        self.harness.update_config(key_values=key_values)

        self.harness.charm._on_certificates_relation_joined(event=event)

        calls = [
            call(cert_type="server", common_name=f"*.{domain}"),
            call(cert_type="server", common_name=f"certifier.{domain}"),
        ]
        patch_request_certificate.assert_has_calls(calls=calls)
