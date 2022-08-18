# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import PropertyMock, call, patch

from ops import testing
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

from charm import FegControlProxyCharm

testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):

    BASE_CERTIFICATES_PATH = "/var/opt/magma/certs"
    BASE_NGHTTPX_CONFIG_PATH = "/var/opt/magma/tmp"

    def setUp(self):
        self.container_name = "magma-feg-control-proxy"
        self.harness = testing.Harness(FegControlProxyCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch(
        "charm.FegControlProxyCharm._controller_certificates_are_stored",
        new_callable=PropertyMock,
    )
    @patch(
        "charm.FegControlProxyCharm._nghttpx_config_is_stored",
        new_callable=PropertyMock,
    )
    @patch("ops.model.Container.exists")
    def test_given_can_connect_to_container_and_nghttpx_config_file_not_stored_and_controller_certificates_neither_when_pebble_ready_then_status_is_waiting(  # noqa: E501
        self,
        patch_file_exists,
        patch_nghttpx_config_is_stored,
        patch_controller_certificates_are_stored,
    ):
        patch_file_exists.return_value = True
        patch_nghttpx_config_is_stored.return_value = False
        patch_controller_certificates_are_stored.return_value = False

        self.harness.charm.on.install.emit()
        self.harness.container_pebble_ready(container_name=self.container_name)

        self.assertEqual(
            self.harness.charm.unit.status,
            WaitingStatus("Waiting for nghttpx config to be available"),
        )

    @patch(
        "charm.FegControlProxyCharm._nghttpx_config_is_stored",
        new_callable=PropertyMock,
    )
    @patch("ops.model.Container.exists")
    def test_given_can_connect_to_container_nghttpx_config_file_not_stored_and_controller_certificates_are_when_pebble_ready_then_status_is_waiting(  # noqa: E501
        self,
        patch_file_exists,
        patch_nghttpx_config_is_stored,
    ):
        patch_file_exists.return_value = True
        patch_nghttpx_config_is_stored.return_value = False

        self.harness.charm.on.install.emit()
        self.harness.container_pebble_ready(container_name=self.container_name)

        self.assertEqual(
            self.harness.model.unit.status,
            WaitingStatus("Waiting for nghttpx config to be available"),
        )

    @patch(
        "charm.FegControlProxyCharm._controller_certificates_are_stored",
        new_callable=PropertyMock,
    )
    @patch("ops.model.Container.exists")
    def test_given_can_connect_to_container_and_nghttpx_config_file_stored_and_controller_certificates_are_not_when_pebble_ready_then_status_is_blocked(  # noqa: E501
        self, patch_file_exists, patch_controller_certificates_are_stored
    ):
        patch_file_exists.return_value = True
        patch_controller_certificates_are_stored.return_value = False

        self.harness.charm.on.install.emit()
        self.harness.container_pebble_ready(container_name=self.container_name)

        self.assertEqual(
            self.harness.model.unit.status,
            BlockedStatus(
                "Provide valid certificates with `juju config feg-control-proxy --file <config_file.yaml>`"
            ),
        )

    @patch("charm.FegControlProxyCharm._push_certificates")
    @patch("ops.model.Container.exec")
    def test_given_can_connect_to_container_when_on_install_then_nghttpx_file_is_created(
        self, patch_exec, patch_push_certificates
    ):
        self.harness.container_pebble_ready(container_name=self.container_name)
        self.harness.charm.on.install.emit()

        patch_exec.assert_has_calls(
            calls=[
                call(command=["/usr/local/bin/generate_nghttpx_config.py"]),
                call().wait_output(),
                call(
                    command=[
                        "sed",
                        "-i",
                        "/errorlog-syslog=/d",
                        f"{self.BASE_NGHTTPX_CONFIG_PATH}/nghttpx.conf",
                    ]
                ),
                call().wait_output(),
            ]
        )

    @patch("ops.model.Container.push")
    @patch("ops.model.Container.exec")
    def test_given_can_connect_to_container_and_nghttpx_config_file_is_stored_when_config_is_provided_then_certificates_are_pushed(
        self, patch_exec, patch_push
    ):
        controller_crt = "whatever controller cert"
        controller_key = "whatever controller key"
        root_ca_key = "whatever rootCA key"
        root_ca_pem = "whatever rootCA pem"
        key_values = {
            "controller-crt": controller_crt,
            "controller-key": controller_key,
            "root-ca-key": root_ca_key,
            "root-ca-pem": root_ca_pem,
        }

        self.harness.container_pebble_ready(container_name=self.container_name)
        self.harness.charm.on.install.emit()
        self.harness.update_config(key_values=key_values)

        patch_exec.assert_has_calls(
            calls=[
                call(command=["mkdir", "-p", self.BASE_CERTIFICATES_PATH]),
                call().wait_output(),
            ]
        )

        patch_push.assert_has_calls(
            calls=[
                call(path=f"{self.BASE_CERTIFICATES_PATH}/controller.crt", source=controller_crt),
                call(path=f"{self.BASE_CERTIFICATES_PATH}/controller.key", source=controller_key),
                call(path=f"{self.BASE_CERTIFICATES_PATH}/rootCA.pem", source=root_ca_pem),
                call(path=f"{self.BASE_CERTIFICATES_PATH}/rootCA.key", source=root_ca_key),
            ]
        )

    @patch("ops.model.Container.push")
    @patch("ops.model.Container.exec")
    @patch("ops.model.Container.exists")
    def test_given_can_connect_to_container_nghttpx_config_file_and_controller_certificates_are_stored_when_pebble_ready_then_control_proxy_service_added_to_pebble_plan(  # noqa: E501
        self, patch_file_exists, patch_exec, patch_push
    ):
        patch_file_exists.return_value = True
        controller_crt = "whatever controller cert"
        controller_key = "whatever controller key"
        root_ca_key = "whatever rootCA key"
        root_ca_pem = "whatever rootCA pem"
        key_values = {
            "controller-crt": controller_crt,
            "controller-key": controller_key,
            "root-ca-key": root_ca_key,
            "root-ca-pem": root_ca_pem,
        }

        self.harness.charm.on.install.emit()
        self.harness.container_pebble_ready(container_name=self.container_name)
        self.harness.update_config(key_values=key_values)
        expected_plan = {
            "services": {
                "magma-feg-control-proxy": {
                    "override": "replace",
                    "summary": "magma-feg-control-proxy",
                    "command": f"nghttpx --conf {self.BASE_NGHTTPX_CONFIG_PATH}/nghttpx.conf "
                    f"{self.BASE_CERTIFICATES_PATH}/controller.key "
                    f"{self.BASE_CERTIFICATES_PATH}/controller.crt",
                    "startup": "enabled",
                }
            },
        }
        updated_plan = self.harness.get_container_pebble_plan("magma-feg-control-proxy").to_dict()

        self.assertEqual(expected_plan, updated_plan)

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.exec")
    @patch("ops.model.Container.push")
    def test_given_can_connect_to_container_and_nghttpx_config_file_and_controller_certificates_are_stored_when_pebble_ready_then_status_is_active(  # noqa: E501
        self, patch_file_exists, patch_exec, patch_push
    ):
        patch_file_exists.return_value = True
        controller_crt = "whatever controller cert"
        controller_key = "whatever controller key"
        root_ca_key = "whatever rootCA key"
        root_ca_pem = "whatever rootCA pem"
        key_values = {
            "controller-crt": controller_crt,
            "controller-key": controller_key,
            "root-ca-key": root_ca_key,
            "root-ca-pem": root_ca_pem,
        }

        self.harness.charm.on.install.emit()
        self.harness.container_pebble_ready(container_name=self.container_name)
        self.harness.update_config(key_values=key_values)

        self.assertEqual(self.harness.model.unit.status, ActiveStatus())
