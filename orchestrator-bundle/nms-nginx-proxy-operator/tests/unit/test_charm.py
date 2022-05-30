# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import patch, Mock

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

    def test_given_when_on_certificates_relation_joined_then_(self):
        event = Mock()

        self.harness.charm._on_certificates_relation_joined(event=event)
        pass