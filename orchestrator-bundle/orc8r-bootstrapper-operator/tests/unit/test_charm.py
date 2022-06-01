# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, call, patch

from ops import testing
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

from charm import MagmaOrc8rBootstrapperCharm

testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    @patch("charm.KubernetesServicePatch", lambda charm, ports, additional_labels: None)
    def setUp(self):
        self.model_name = "whatever"
        self.harness = testing.Harness(MagmaOrc8rBootstrapperCharm)
        self.harness.set_model_name(name=self.model_name)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.maxDiff = None

    def test_given_no_relations_established_when_pebble_ready_then_status_is_blocked(self):
        self.harness.container_pebble_ready(container_name="magma-orc8r-bootstrapper")

        self.assertEqual(
            self.harness.charm.unit.status,
            BlockedStatus("Waiting for certificates relation"),
        )

    def test_given_certs_arent_stored_when_pebble_ready_then_status_is_blocked(self):
        relation_id = self.harness.add_relation(
            relation_name="certificates", remote_app="vault-k8s"
        )
        self.harness.add_relation_unit(relation_id, "vault-k8s/0")

        self.harness.container_pebble_ready(container_name="magma-orc8r-bootstrapper")

        self.assertEqual(
            self.harness.charm.unit.status,
            WaitingStatus("Waiting for certs to be available"),
        )

    @patch("ops.model.Container.exists")
    def test_given_relations_created_and_certs_are_stored_when_pebble_ready_then_pebble_service_is_created(  # noqa: E501
        self, patch_file_exists
    ):
        patch_file_exists.return_value = True
        relation_id = self.harness.add_relation(
            relation_name="certificates", remote_app="vault-k8s"
        )
        self.harness.add_relation_unit(relation_id=relation_id, remote_unit_name="vault-k8s/0")
        expected_plan = {
            "services": {
                "magma-orc8r-bootstrapper": {
                    "override": "replace",
                    "startup": "enabled",
                    "command": "/usr/bin/envdir "
                    "/var/opt/magma/envdir "
                    "/var/opt/magma/bin/bootstrapper "
                    "-cak=/var/opt/magma/certs/bootstrapper.key "
                    "-logtostderr=true "
                    "-v=0",
                    "environment": {
                        "SERVICE_REGISTRY_MODE": "k8s",
                        "SERVICE_REGISTRY_NAMESPACE": self.model_name,
                    },
                },
            },
        }

        self.harness.container_pebble_ready("magma-orc8r-bootstrapper")

        updated_plan = self.harness.get_container_pebble_plan("magma-orc8r-bootstrapper").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    @patch("ops.model.Container.exists")
    def test_given_relations_created_and_certs_are_stored_when_pebble_ready_then_status_is_active(
        self, patch_container_exists
    ):
        relation_id = self.harness.add_relation(
            relation_name="certificates", remote_app="vault-k8s"
        )
        self.harness.add_relation_unit(relation_id=relation_id, remote_unit_name="vault-k8s/0")
        patch_container_exists.return_value = True

        self.harness.container_pebble_ready("magma-orc8r-bootstrapper")

        self.assertEqual(self.harness.charm.unit.status, ActiveStatus())

    @patch("ops.model.Container.push")
    @patch("ops.model.Container.exists")
    def test_given_certs_arent_yet_stored_when_on_certificate_available_then_certs_are_stored(
        self, patch_file_exists, patch_push
    ):
        common_name = "whatever.domain"
        private_key = "whatever private key"
        patch_file_exists.return_value = False
        event = Mock()
        event.certificate_data = {"common_name": common_name, "key": private_key}
        self.harness.container_pebble_ready(container_name="magma-orc8r-bootstrapper")

        self.harness.charm._on_certificate_available(event=event)

        path = "/var/opt/magma/certs/bootstrapper.key"
        calls = [call(path=path, source=private_key)]
        patch_push.assert_has_calls(calls=calls)

    @patch(
        "charms.tls_certificates_interface.v0.tls_certificates.InsecureCertificatesRequires.request_certificate"  # noqa: E501,W505
    )
    def test_given_certificates_charm_when_certificates_relation_joined_then_certificate_is_requested(  # noqa: E501
        self, patch_request_certificate
    ):
        event = Mock()

        self.harness.charm._on_certificates_relation_joined(event=event)

        calls = [call(cert_type="server", common_name="whatever.domain")]
        patch_request_certificate.assert_has_calls(calls=calls)
