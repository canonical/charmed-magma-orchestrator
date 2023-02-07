# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import io
import unittest
from copy import deepcopy
from unittest.mock import Mock, patch

from ops import testing
from ops.model import BlockedStatus, WaitingStatus
from ops.pebble import PathError, ProtocolError

from charm import MagmaOrc8rNginxCharm

TEST_APP_NAME = "whatever"
TEST_DOMAIN = "example.com"
TEST_ROOT_CA_PEM_STRING = "thisisjustatest"
TEST_ROOT_CA_PEM = io.StringIO(TEST_ROOT_CA_PEM_STRING)
TEST_CERTIFIER_PEM_STRING = "whatever certifier pem"
TEST_CERTIFIER_PEM = io.StringIO(TEST_CERTIFIER_PEM_STRING)


class TestOrchestratorRelation(unittest.TestCase):
    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports, service_type, service_name, additional_labels, additional_selectors: None,  # noqa: E501
    )
    def setUp(self):
        self.model_name = "whatever"
        self.harness = testing.Harness(MagmaOrc8rNginxCharm)
        self.harness.set_model_name(name=self.model_name)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_given_unit_not_leader_when_orchestrator_relation_joined_then_relation_data_bag_is_not_updated(  # noqa: E501
        self,
    ):
        orchestrator_relation_id = self._create_orchestrator_relation(TEST_APP_NAME)

        self.assertEqual(
            self.harness.get_relation_data(orchestrator_relation_id, TEST_APP_NAME),
            {},
        )

    @patch("ops.model.Container.exec", Mock())
    def test_given_invalid_domain_when_orchestrator_relation_joined_then_charm_goes_to_blocked_status(  # noqa: E501
        self,
    ):
        self.harness.set_leader(is_leader=True)
        self.harness.update_config(key_values={"domain": "invalid"})

        _ = self._create_orchestrator_relation(TEST_APP_NAME)

        assert self.harness.charm.unit.status == BlockedStatus("Domain config is not valid")

    @patch("ops.model.Container.exec", Mock())
    def test_given_magma_orc8r_nginx_service_not_running_when_orchestrator_relation_joined_then_charm_goes_to_waiting_status(  # noqa: E501
        self,
    ):
        self.harness.set_leader(is_leader=True)
        self.harness.update_config(key_values={"domain": TEST_DOMAIN})

        _ = self._create_orchestrator_relation(TEST_APP_NAME)

        assert self.harness.charm.unit.status == WaitingStatus(
            "Waiting for magma-orc8r-nginx service to become active"
        )

    @patch("ops.model.Container.get_service", new=Mock())
    @patch("ops.model.Container.exec", Mock())
    def test_given_magma_orc8r_nginx_service_active_but_rootca_not_stored_when_orchestrator_relation_joined_then_charm_goes_to_waiting_status(  # noqa: E501
        self,
    ):
        self.harness.set_can_connect(container="magma-orc8r-nginx", val=True)
        self.harness.set_leader(is_leader=True)
        self.harness.update_config(key_values={"domain": TEST_DOMAIN})

        _ = self._create_orchestrator_relation(TEST_APP_NAME)

        assert self.harness.charm.unit.status == WaitingStatus(
            "Waiting for rootCA certificate to be available"
        )

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.get_service", new=Mock())
    @patch("ops.model.Container.exec", Mock())
    def test_given_magma_orc8r_nginx_service_active_but_certifier_pem_not_stored_when_orchestrator_relation_joined_then_charm_goes_to_waiting_status(  # noqa: E501
        self, patch_exists
    ):
        self.harness.set_can_connect(container="magma-orc8r-nginx", val=True)
        self.harness.set_leader(is_leader=True)
        self.harness.update_config(key_values={"domain": TEST_DOMAIN})
        patch_exists.side_effect = [True, False]

        _ = self._create_orchestrator_relation(TEST_APP_NAME)

        assert self.harness.charm.unit.status == WaitingStatus(
            "Waiting for `certifier.pem` certificate to be available"
        )

    @patch("ops.model.Container.pull")
    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.get_service", new=Mock())
    @patch("ops.model.Container.exec", Mock())
    def test_given_path_error_when_orchestrator_relation_joined_then_pulling_rootca_from_container_fails_and_charm_goes_to_blocked_status(  # noqa: E501
        self, patched_exists, patched_pull
    ):
        self.harness.set_leader(is_leader=True)
        self.harness.update_config(key_values={"domain": TEST_DOMAIN})
        self.harness.set_can_connect(container="magma-orc8r-nginx", val=True)
        patched_exists.return_value = True
        patched_pull.side_effect = PathError("what", "ever")

        _ = self._create_orchestrator_relation(TEST_APP_NAME)

        assert self.harness.charm.unit.status == BlockedStatus(
            "Failed to pull certs from the container"
        )

    @patch("ops.model.Container.pull")
    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.get_service", new=Mock())
    @patch("ops.model.Container.exec", Mock())
    def test_given_protocol_error_when_pulling_rootca_when_orchestrator_relation_joined_then_pulling_rootca_from_container_fails_and_relevant_message_is_logged(  # noqa: E501
        self, patched_exists, patched_pull
    ):
        self.harness.set_leader(is_leader=True)
        self.harness.update_config(key_values={"domain": TEST_DOMAIN})
        self.harness.set_can_connect(container="magma-orc8r-nginx", val=True)
        patched_exists.return_value = True
        patched_pull.side_effect = ProtocolError()

        _ = self._create_orchestrator_relation(TEST_APP_NAME)

        assert self.harness.charm.unit.status == BlockedStatus(
            "Failed to pull certs from the container"
        )

    @patch("ops.model.Container.pull")
    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.get_service", new=Mock())
    @patch("ops.model.Container.exec", Mock())
    def test_given_all_checks_passed_when_orchestrator_relation_joined_then_relation_data_bag_is_updated(  # noqa: E501
        self, patched_exists, patched_pull
    ):
        self.harness.set_leader(is_leader=True)
        self.harness.update_config(key_values={"domain": TEST_DOMAIN})
        self.harness.set_can_connect(container="magma-orc8r-nginx", val=True)
        patched_exists.return_value = True
        patched_pull.side_effect = [deepcopy(TEST_ROOT_CA_PEM), deepcopy(TEST_CERTIFIER_PEM)]

        orchestrator_relation_id = self._create_orchestrator_relation(TEST_APP_NAME)

        self.assertEqual(
            self.harness.get_relation_data(orchestrator_relation_id, self.harness.charm.app),
            self._generate_expected_relation_data(
                TEST_ROOT_CA_PEM_STRING, TEST_CERTIFIER_PEM_STRING, TEST_DOMAIN
            ),
        )

    @patch("ops.model.Container.pull")
    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.get_service", new=Mock())
    @patch("ops.model.Container.exec", Mock())
    def test_given_orchestrator_relation_created_and_orchestrator_details_in_the_relation_data_bag_when_domain_changes_then_relation_data_bag_is_updated(  # noqa: E501
        self, patched_exists, patched_pull
    ):
        test_new_domain = "whatever.else.com"
        self.harness.set_can_connect(container="magma-orc8r-nginx", val=True)
        self.harness.set_leader(is_leader=True)
        self.harness.update_config(key_values={"domain": TEST_DOMAIN})
        patched_exists.return_value = True
        patched_pull.side_effect = [
            deepcopy(TEST_ROOT_CA_PEM),
            deepcopy(TEST_CERTIFIER_PEM),
            deepcopy(TEST_ROOT_CA_PEM),
            deepcopy(TEST_CERTIFIER_PEM),
        ]
        orchestrator_relation_id = self._create_orchestrator_relation(TEST_APP_NAME)
        self.assertEqual(
            self.harness.get_relation_data(orchestrator_relation_id, self.harness.charm.app),
            self._generate_expected_relation_data(
                TEST_ROOT_CA_PEM_STRING, TEST_CERTIFIER_PEM_STRING, TEST_DOMAIN
            ),
        )

        self.harness.update_config(key_values={"domain": test_new_domain})

        self.assertEqual(
            self.harness.get_relation_data(orchestrator_relation_id, self.harness.charm.app),
            self._generate_expected_relation_data(
                TEST_ROOT_CA_PEM_STRING, TEST_CERTIFIER_PEM_STRING, test_new_domain
            ),
        )

    @patch("ops.model.Container.pull")
    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.get_service", new=Mock())
    @patch("ops.model.Container.exec", Mock())
    @patch("ops.model.Container.push", Mock())
    def test_given_orchestrator_relation_created_and_orchestrator_details_in_the_relation_data_bag_when_root_ca_certificate_updated_then_relation_data_bag_is_updated(  # noqa: E501
        self, patched_exists, patched_pull
    ):
        test_rootca_cert_string = "some cert"
        test_rootca_cert = io.StringIO(test_rootca_cert_string)
        self.harness.set_leader(is_leader=True)
        self.harness.update_config(key_values={"domain": TEST_DOMAIN})
        self.harness.set_can_connect(container="magma-orc8r-nginx", val=True)
        patched_exists.return_value = True
        patched_pull.side_effect = [
            deepcopy(TEST_ROOT_CA_PEM),
            deepcopy(TEST_CERTIFIER_PEM),
            test_rootca_cert,
            deepcopy(TEST_CERTIFIER_PEM),
        ]
        orchestrator_relation_id = self._create_orchestrator_relation(TEST_APP_NAME)
        self.assertEqual(
            self.harness.get_relation_data(orchestrator_relation_id, self.harness.charm.app),
            self._generate_expected_relation_data(
                TEST_ROOT_CA_PEM_STRING, TEST_CERTIFIER_PEM_STRING, TEST_DOMAIN
            ),
        )

        self.harness.charm._cert_root_ca.on.certificate_available.emit(
            certificate=test_rootca_cert_string,
        )

        self.assertEqual(
            self.harness.get_relation_data(orchestrator_relation_id, self.harness.charm.app),
            self._generate_expected_relation_data(
                test_rootca_cert_string, TEST_CERTIFIER_PEM_STRING, TEST_DOMAIN
            ),
        )

    @patch("ops.model.Container.pull")
    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.get_service", new=Mock())
    @patch("ops.model.Container.exec", Mock())
    @patch("ops.model.Container.push", Mock())
    def test_given_orchestrator_relation_created_and_orchestrator_details_in_the_relation_data_bag_when_certifier_pem_certificate_updated_then_relation_data_bag_is_updated(  # noqa: E501
        self, patched_exists, patched_pull
    ):
        test_certifier_pem_string = "whatever changed certifier pem"
        test_certifier_pem = io.StringIO(test_certifier_pem_string)
        self.harness.set_leader(is_leader=True)
        self.harness.update_config(key_values={"domain": TEST_DOMAIN})
        self.harness.set_can_connect(container="magma-orc8r-nginx", val=True)
        patched_exists.return_value = True
        patched_pull.side_effect = [
            deepcopy(TEST_ROOT_CA_PEM),
            deepcopy(TEST_CERTIFIER_PEM),
            deepcopy(TEST_ROOT_CA_PEM),
            test_certifier_pem,
        ]
        orchestrator_relation_id = self._create_orchestrator_relation(TEST_APP_NAME)
        self.assertEqual(
            self.harness.get_relation_data(orchestrator_relation_id, self.harness.charm.app),
            self._generate_expected_relation_data(
                TEST_ROOT_CA_PEM_STRING, TEST_CERTIFIER_PEM_STRING, TEST_DOMAIN
            ),
        )

        self.harness.charm._cert_certifier.on.certificate_available.emit(
            certificate=test_certifier_pem_string,
        )

        self.assertEqual(
            self.harness.get_relation_data(orchestrator_relation_id, self.harness.charm.app),
            self._generate_expected_relation_data(
                TEST_ROOT_CA_PEM_STRING, test_certifier_pem_string, TEST_DOMAIN
            ),
        )

    @staticmethod
    def _generate_expected_relation_data(
        root_ca_pem: str, certifier_pem_certificate: str, domain: str
    ) -> dict:
        return {
            "root_ca_certificate": root_ca_pem,
            "certifier_pem_certificate": certifier_pem_certificate,
            "orchestrator_address": f"controller.{domain}",
            "orchestrator_port": "443",
            "bootstrapper_address": f"bootstrapper-controller.{domain}",
            "bootstrapper_port": "443",
            "fluentd_address": f"fluentd.{domain}",
            "fluentd_port": "24224",
        }

    def _create_orchestrator_relation(self, app_name: str) -> int:
        orchestrator_relation_id = self.harness.add_relation(
            relation_name="orchestrator", remote_app=app_name
        )
        self.harness.add_relation_unit(
            relation_id=orchestrator_relation_id,
            remote_unit_name="whatever/0",
        )
        return orchestrator_relation_id
