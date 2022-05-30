# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, call, patch

from ops import testing
from ops.model import ActiveStatus, BlockedStatus

from charm import MagmaNmsNginxProxyCharm

testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports, service_type, service_name, additional_labels: None,
    )
    def setUp(self):
        self.harness = testing.Harness(MagmaNmsNginxProxyCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_given_bad_domain_config_when_pebble_ready_then_status_is_blocked(self):
        key_values = {"domain": ""}
        self.harness.update_config(key_values=key_values)

        self.harness.container_pebble_ready(container_name="magma-nms-nginx-proxy")

        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Config 'domain' is not valid"),
        )

    def test_given_magmalte_relation_not_created_when_pebble_ready_then_status_is_blocked(self):
        key_values = {"domain": "whatever.com"}
        self.harness.update_config(key_values=key_values)
        self.harness.add_relation(relation_name="certificates", remote_app="orc8r-certifier")

        self.harness.container_pebble_ready(container_name="magma-nms-nginx-proxy")

        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for magmalte relation to be created"),
        )

    def test_given_certificates_relation_not_created_when_pebble_ready_then_status_is_blocked(
        self,
    ):
        key_values = {"domain": "whatever.com"}
        self.harness.update_config(key_values=key_values)
        self.harness.add_relation(relation_name="magmalte", remote_app="orc8r-certifier")

        self.harness.container_pebble_ready(container_name="magma-nms-nginx-proxy")

        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for certificates relation to be created"),
        )

    @patch("ops.model.Container.exists")
    def test_given_correct_domain_and_relations_created_when_pebble_ready_then_status_is_active(
        self, patch_file_exists
    ):
        patch_file_exists.return_value = True
        key_values = {"domain": "whatever.com"}
        self.harness.update_config(key_values=key_values)
        self.harness.add_relation(relation_name="certificates", remote_app="orc8r-certifier")
        self.harness.add_relation(relation_name="magmalte", remote_app="nms-magmalte")

        self.harness.container_pebble_ready(container_name="magma-nms-nginx-proxy")

        self.assertEqual(
            self.harness.charm.unit.status,
            ActiveStatus(),
        )

    @patch("ops.model.Container.exists")
    def test_given_correct_domain_and_relations_created_when_pebble_ready_then_pebble_service_is_created(  # noqa: E501
        self, patch_file_exists
    ):
        container_name = service_name = "magma-nms-nginx-proxy"
        patch_file_exists.return_value = True
        key_values = {"domain": "whatever.com"}
        self.harness.update_config(key_values=key_values)
        self.harness.add_relation(relation_name="certificates", remote_app="orc8r-certifier")
        self.harness.add_relation(relation_name="magmalte", remote_app="nms-magmalte")

        self.harness.container_pebble_ready(container_name=container_name)

        expected_plan = {
            "services": {
                service_name: {
                    "startup": "enabled",
                    "override": "replace",
                    "command": "nginx",
                }
            }
        }
        updated_plan = self.harness.get_container_pebble_plan(container_name).to_dict()
        self.assertEqual(expected_plan, updated_plan)

    @patch("ops.model.Container.push")
    def test_given_pebble_ready_when_on_install_then_(self, patch_push):
        self.harness.container_pebble_ready(container_name="magma-nms-nginx-proxy")

        self.harness.charm.on.install.emit()

        args, kwargs = patch_push.call_args

        config_file = (
            "server {\n"
            "listen 443;\n"
            "ssl on;\n"
            "ssl_certificate /etc/nginx/conf.d/nms_nginx.pem;\n"
            "ssl_certificate_key /etc/nginx/conf.d/nms_nginx.key.pem;\n"
            "location / {\n"
            "proxy_pass http://magmalte:8081;\n"
            "proxy_set_header Host $http_host;\n"
            "proxy_set_header X-Forwarded-Proto $scheme;\n"
            "}\n"
            "}"
        )
        self.assertEqual("/etc/nginx/conf.d/nginx_proxy_ssl.conf", kwargs["path"])
        self.assertEqual(config_file, kwargs["source"])

    @patch(
        "charms.tls_certificates_interface.v0.tls_certificates.InsecureCertificatesRequires.request_certificate"  # noqa: E501, W505
    )
    def test_given_domain_name_in_config_when_on_certificates_relation_joined_then_certificate_is_requested(  # noqa: E501
        self, patch_request_certificate
    ):
        domain_name = "whatever.com"
        key_values = {"domain": domain_name}
        self.harness.update_config(key_values=key_values)
        event = Mock()

        self.harness.charm._on_certificates_relation_joined(event=event)

        args, kwargs = patch_request_certificate.call_args
        self.assertEqual("server", kwargs["cert_type"])
        self.assertEqual(domain_name, kwargs["common_name"])

    @patch("ops.model.Container.push")
    @patch("ops.model.Container.can_connect")
    @patch("ops.model.Container.exists")
    def test_given_certificates_arent_stored_when_on_certificates_available_then_certificate_and_key_are_stored(  # noqa: E501
        self, patch_file_exists, patch_can_connect, patch_push
    ):
        patch_can_connect.return_value = True
        patch_file_exists.return_value = False
        certificate = "whatever certificate"
        private_key = "whatever private key"
        domain_name = "whatever.com"
        key_values = {"domain": domain_name}
        self.harness.update_config(key_values=key_values)
        event = Mock()
        event.certificate_data = {
            "common_name": domain_name,
            "cert": certificate,
            "key": private_key,
        }

        self.harness.charm._on_certificate_available(event=event)

        calls = [
            call(path="/etc/nginx/conf.d/nms_nginx.pem", source=certificate),
            call(path="/etc/nginx/conf.d/nms_nginx.key.pem", source=private_key),
        ]
        patch_push.assert_has_calls(calls=calls)
