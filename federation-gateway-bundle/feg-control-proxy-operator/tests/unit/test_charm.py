# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, PropertyMock, patch

from ops import testing
from ops.model import ActiveStatus, WaitingStatus

from charm import FegControlProxyCharm

testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):

    BASE_CERTS_PATH = "/var/opt/magma/certs"
    BASE_NGHTTPX_CONFIG_PATH = "/var/opt/magma/tmp"

    def setUp(self):
        self.container_name = "magma-feg-control-proxy"
        self.harness = testing.Harness(FegControlProxyCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch("charm.FegControlProxyCharm._controller_certs_are_stored", new_callable=PropertyMock)
    @patch("charm.FegControlProxyCharm._nghttpx_config_is_stored", new_callable=PropertyMock)
    @patch("ops.model.Container.exec", new=Mock())
    @patch("ops.model.Container.exists")
    def test_given_can_connect_to_container_when_pebble_ready_and_nghttpx_config_file_not_created_and_controller_certs_neither_then_status_is_waiting(  # noqa: E501
        self, patch_file_exists, patch_nghttpx_config_is_stored, patch_controller_certs_are_stored
    ):
        patch_file_exists.return_value = True
        patch_nghttpx_config_is_stored.return_value = False
        patch_controller_certs_are_stored.return_value = False

        self.harness.charm.on.install.emit()
        self.harness.container_pebble_ready(container_name=self.container_name)

        self.assertEqual(
            self.harness.charm.unit.status,
            WaitingStatus("Waiting for nghttpx config to be available"),
        )

    @patch("charm.FegControlProxyCharm._nghttpx_config_is_stored", new_callable=PropertyMock)
    @patch("ops.model.Container.exec", new=Mock())
    @patch("ops.model.Container.exists")
    def test_given_can_connect_to_container_when_pebble_ready_and_nghttpx_config_file_not_created_and_controller_certs_are_then_status_is_waiting(  # noqa: E501
        self, patch_file_exists, patch_nghttpx_config_is_stored
    ):
        patch_file_exists.return_value = True
        patch_nghttpx_config_is_stored.return_value = False

        self.harness.charm.on.install.emit()
        self.harness.container_pebble_ready(container_name=self.container_name)

        self.assertEqual(
            self.harness.model.unit.status,
            WaitingStatus("Waiting for nghttpx config to be available"),
        )

    @patch("charm.FegControlProxyCharm._controller_certs_are_stored", new_callable=PropertyMock)
    @patch("ops.model.Container.exec", new=Mock())
    @patch("ops.model.Container.exists")
    def test_given_can_connect_to_container_when_pebble_ready_and_nghttpx_config_file_created_and_controller_certs_are_not_then_status_is_waiting(  # noqa: E501
        self, patch_file_exists, patch_controller_certs_are_stored
    ):
        patch_file_exists.return_value = True
        patch_controller_certs_are_stored.return_value = False

        self.harness.charm.on.install.emit()
        self.harness.container_pebble_ready(container_name=self.container_name)

        self.assertEqual(
            self.harness.model.unit.status,
            WaitingStatus("Waiting for controller certs to be available"),
        )

    @patch("ops.model.Container.exec", new=Mock())
    @patch("ops.model.Container.exists")
    def test_given_can_connect_to_container_when_pebble_ready_and_nghttpx_config_file_and_controller_certs_are_created_then_status_is_active(  # noqa: E501
        self, patch_file_exists
    ):
        patch_file_exists.return_value = True

        self.harness.charm.on.install.emit()
        self.harness.container_pebble_ready(container_name=self.container_name)

        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    @patch("ops.model.Container.exec", new=Mock())
    @patch("ops.model.Container.exists")
    def test_given_can_connect_to_container_when_pebble_ready_nghttpx_config_file_and_controller_certs_are_created_then_control_proxy_service_added_to_pebble_plan(  # noqa: E501
        self, patch_file_exists
    ):
        patch_file_exists.return_value = True
        self.harness.charm.on.install.emit()

        self.harness.container_pebble_ready(container_name=self.container_name)
        expected_plan = {
            "services": {
                "magma-feg-control-proxy": {
                    "override": "replace",
                    "summary": "magma-feg-control-proxy",
                    "command": "nghttpx --conf /var/opt/magma/tmp/nghttpx.conf "
                    "/var/opt/magma/certs/controller.key "
                    "/var/opt/magma/certs/controller.crt",
                    "startup": "enabled",
                }
            },
        }
        updated_plan = self.harness.get_container_pebble_plan("magma-feg-control-proxy").to_dict()

        self.assertEqual(expected_plan, updated_plan)
