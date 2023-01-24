# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, call, patch

from ops import testing
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.pebble import Layer

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

    @patch("ops.model.Container.exists")
    def test_given_cert_controller_relation_not_created_when_pebble_ready_event_emitted_then_unit_is_in_blocked_state(  # noqa: E501
        self, patch_exists
    ):
        self.harness.add_relation(
            relation_name="magma-nms-magmalte", remote_app="magma-nms-magmalte"
        )
        patch_exists.return_value = True

        self.harness.set_can_connect("magma-nms-nginx-proxy", True)

        self.harness.container_pebble_ready("magma-nms-nginx-proxy")

        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for cert-controller relation to be created"),
        )

    @patch("ops.model.Container.exists")
    def test_given_nms_magmalte_relation_not_created_when_pebble_ready_event_emitted_then_unit_is_in_blocked_state(  # noqa: E501
        self, patch_exists
    ):
        self.harness.add_relation(
            relation_name="cert-controller", remote_app="magma-orc8r-certifier"
        )
        patch_exists.return_value = True

        self.harness.set_can_connect("magma-nms-nginx-proxy", True)

        self.harness.container_pebble_ready("magma-nms-nginx-proxy")

        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for magmalte relation to be created"),
        )

    @patch("ops.model.Container.exists")
    def test_given_required_relations_are_created_but_certs_are_not_stored_when_pebble_ready_event_emitted_then_unit_is_in_waiting_state(  # noqa: E501
        self, patch_exists
    ):
        self.harness.add_relation(
            relation_name="magma-nms-magmalte", remote_app="magma-nms-magmalte"
        )
        self.harness.add_relation(
            relation_name="cert-controller", remote_app="magma-orc8r-certifier"
        )
        patch_exists.return_value = False

        self.harness.set_can_connect("magma-nms-nginx-proxy", True)

        self.harness.container_pebble_ready("magma-nms-nginx-proxy")

        self.assertEqual(
            self.harness.charm.unit.status, WaitingStatus("Waiting for certs to be available")
        )

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.exec")
    def test_given_required_relations_are_created_and_certs_are_stored_when_pebble_ready_event_emitted_then_pebble_is_configured_with_correct_plan(  # noqa: E501
        self, patched_exec, patch_exists
    ):
        patched_exec.return_value = MockExec()
        self.harness.add_relation(
            relation_name="magma-nms-magmalte", remote_app="magma-nms-magmalte"
        )
        self.harness.add_relation(
            relation_name="cert-controller", remote_app="magma-orc8r-certifier"
        )
        patch_exists.return_value = True
        expected_plan = {
            "services": {
                "magma-nms-nginx-proxy": {
                    "override": "replace",
                    "startup": "enabled",
                    "command": "nginx",
                }
            }
        }

        self.harness.container_pebble_ready("magma-nms-nginx-proxy")

        updated_plan = self.harness.get_container_pebble_plan("magma-nms-nginx-proxy").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.exec")
    def test_workload_without_pebble_layer_applied_when_pebble_ready_then_nginx_is_reloaded(
        self, patched_exec, patch_exists
    ):
        test_nginx_pid = "1234"
        patch_exists.return_value = True
        patched_exec.return_value = MockExec(stdout=test_nginx_pid)
        self.harness.add_relation(
            relation_name="magma-nms-magmalte", remote_app="magma-nms-magmalte"
        )
        self.harness.add_relation(
            relation_name="cert-controller", remote_app="magma-orc8r-certifier"
        )

        self.harness.container_pebble_ready("magma-nms-nginx-proxy")

        patched_exec.assert_has_calls(
            [call(["cat", "/var/run/nginx.pid"]), call(["kill", "-HUP", test_nginx_pid])]
        )

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.exec")
    def test_workload_with_pebble_layer_already_applied_when_pebble_ready_then_nginx_is_reloaded(
        self, patched_exec, patch_exists
    ):
        test_nginx_pid = "1234"
        patch_exists.return_value = True
        patched_exec.return_value = MockExec(stdout=test_nginx_pid)
        nms_nginx_container = self.harness.charm.unit.get_container("magma-nms-nginx-proxy")
        self.harness.set_can_connect(container=nms_nginx_container, val=True)
        self.harness.add_relation(
            relation_name="magma-nms-magmalte", remote_app="magma-nms-magmalte"
        )
        self.harness.add_relation(
            relation_name="cert-controller", remote_app="magma-orc8r-certifier"
        )
        test_pebble_layer = Layer(
            {
                "services": {
                    "magma-nms-nginx-proxy": {
                        "override": "replace",
                        "startup": "enabled",
                        "command": "nginx",
                    }
                }
            }
        )
        nms_nginx_container.add_layer("magma-nms-nginx-proxy", test_pebble_layer, combine=True)

        self.harness.container_pebble_ready("magma-nms-nginx-proxy")

        patched_exec.assert_has_calls(
            [call(["cat", "/var/run/nginx.pid"]), call(["kill", "-HUP", test_nginx_pid])]
        )

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.exec")
    def test_given_required_relations_are_created_and_certs_are_stored_when_pebble_ready_event_emitted_then_status_is_active(  # noqa: E501
        self, patched_exec, patch_exists
    ):
        patched_exec.return_value = MockExec()
        self.harness.add_relation(
            relation_name="magma-nms-magmalte", remote_app="magma-nms-magmalte"
        )
        self.harness.add_relation(
            relation_name="cert-controller", remote_app="magma-orc8r-certifier"
        )
        patch_exists.return_value = True

        self.harness.container_pebble_ready("magma-nms-nginx-proxy")

        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())

    @patch("ops.model.Container.push")
    @patch("ops.model.Container.exec", Mock())
    def test_given_pebble_ready_when_on_install_then_nginx_config_is_stored(self, patch_push):
        self.harness.container_pebble_ready(container_name="magma-nms-nginx-proxy")

        self.harness.charm.on.install.emit()

        patch_push.assert_called_with(
            path="/etc/nginx/conf.d/nginx_proxy_ssl.conf",
            source=(
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
            ),
        )

    @patch("ops.model.Container.push")
    def test_given_pebble_ready_when_on_certificate_available_then_certificates_are_pushed_to_workload(  # noqa: E501
        self, patch_push
    ):
        certificate = "whatever cert"
        private_key = "whatever private key"
        container = self.harness.model.unit.get_container("magma-nms-nginx-proxy")
        self.harness.set_can_connect(container=container, val=True)
        event = Mock()
        event.certificate = certificate
        event.private_key = private_key

        self.harness.charm._on_certificate_available(event)

        calls = [
            call(path="/etc/nginx/conf.d/nms_nginx.pem", source=certificate),
            call(path="/etc/nginx/conf.d/nms_nginx.key.pem", source=private_key),
        ]
        patch_push.assert_has_calls(calls=calls)


class MockExec:
    def __init__(self, stdout="test stdout", stderr="test stderr"):
        self.wait_output_stdout = stdout
        self.wait_output_stderr = stderr

    def exec(self, *args, **kwargs):
        pass

    def wait_output(self):
        return self.wait_output_stdout, self.wait_output_stderr
