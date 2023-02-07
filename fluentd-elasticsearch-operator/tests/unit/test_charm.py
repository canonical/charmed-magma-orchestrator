# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from pathlib import Path
from typing import Mapping, Tuple, Union
from unittest.mock import Mock, PropertyMock, call, mock_open, patch

from charms.tls_certificates_interface.v1.tls_certificates import (
    generate_ca,
    generate_certificate,
    generate_csr,
    generate_private_key,
)
from ops import testing
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

from charm import FluentdElasticsearchCharm

TEST_DOMAIN = "example.com"
TEST_ES_URL = "testes:1234"
TEST_FLUENTD_CHUNK_LIMIT = "size"
TEST_FLUENTD_QUEUE_LIMIT = 4321
VALID_TEST_CHARM_CONFIG: Mapping[str, Union[str, int]] = {
    "domain": TEST_DOMAIN,
    "elasticsearch-url": TEST_ES_URL,
    "fluentd-chunk-limit-size": TEST_FLUENTD_CHUNK_LIMIT,
    "fluentd-queue-limit-length": TEST_FLUENTD_QUEUE_LIMIT,
}
VALID_TEST_CHARM_CONFIG_YAML = f"""options:
  domain:
    type: string
    default: {TEST_DOMAIN}
  elasticsearch-url:
    type: string
    default: {TEST_ES_URL}
  fluentd-chunk-limit-size:
    type: string
    default: 2M
  fluentd-queue-limit-length:
    type: int
    default: 8
"""
TEST_FORWARD_INPUT_CONF_TEMPLATE = b"{{ certs_directory }}"
TEST_OUTPUT_CONF_TEMPLATE = b"""{{ elasticsearch_host }}
{{ elasticsearch_port }}
{{ fluentd_chunk_limit_size }}
{{ fluentd_queue_limit_length }}
"""
TLS_CERTIFICATES_LIB = "charms.tls_certificates_interface.v1.tls_certificates"


class TestCharm(unittest.TestCase):
    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports, service_type: None,
    )
    def setUp(self):
        self.harness = testing.Harness(
            FluentdElasticsearchCharm,
            config=VALID_TEST_CHARM_CONFIG_YAML,
        )
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.harness.container_pebble_ready(container_name="fluentd")

    def test_given_workload_container_not_ready_when_install_then_status_is_waiting(self):
        self.harness.set_can_connect("fluentd", False)

        self.harness.charm.on.install.emit()

        assert self.harness.charm.unit.status == WaitingStatus("Waiting for container to be ready")

    def test_given_peer_relation_not_created_when_install_then_status_is_waiting(self):
        self.harness.charm.on.install.emit()

        assert self.harness.charm.unit.status == WaitingStatus(
            "Waiting for replicas relation to be created"
        )

    @patch("charm.generate_private_key")
    @patch("ops.model.Container.push", Mock())
    def test_given_fluentd_container_ready_and_peer_relation_created_and_unit_is_leader_when_install_then_private_key_is_generated_and_saved_in_the_peer_relation_data(  # noqa: E501
        self, patched_generate_private_key
    ):
        self.harness.set_leader(is_leader=True)
        test_private_key = b"testprivatekey"
        patched_generate_private_key.return_value = test_private_key
        peer_relation_id, _ = self._create_peer_relation_with_certificates(
            domain_config=TEST_DOMAIN
        )

        self.harness.charm.on.install.emit()

        patched_generate_private_key.assert_called_once()
        self.assertEqual(
            self.harness.get_relation_data(peer_relation_id, self.harness.charm.app.name),
            {"fluentd_private_key": test_private_key.decode()},
        )

    @patch("charm.generate_private_key")
    @patch("ops.model.Container.push", Mock())
    def test_given_fluentd_container_ready_and_peer_relation_created_and_unit_is_not_leader_when_install_then_private_key_is_not_generated(  # noqa: E501
        self, patched_generate_private_key
    ):
        self._create_peer_relation_with_certificates(domain_config=TEST_DOMAIN)

        self.harness.charm.on.install.emit()

        patched_generate_private_key.assert_not_called()

    @patch("ops.model.Container.push")
    @patch("builtins.open", new_callable=mock_open())
    @patch("charm.FluentdElasticsearchCharm.CERTIFICATES_DIRECTORY", new_callable=PropertyMock)
    def test_given_fluentd_container_ready_and_peer_relation_created_when_install_then_static_configs_are_pushed_to_the_workload_container(  # noqa: E501
        self, patched_certs_dir, patched_open, patched_push
    ):
        test_certs_path = "/test/path"
        patched_certs_dir.return_value = test_certs_path
        self._create_peer_relation_with_certificates(domain_config=TEST_DOMAIN)
        test_fluentd_configs = [
            "config one",
            "config two",
            TEST_FORWARD_INPUT_CONF_TEMPLATE,
        ]
        patched_open.side_effect = [
            mock_open(read_data=content).return_value for content in test_fluentd_configs
        ]
        expected_rendered_test_forward_input_conf = test_certs_path

        self.harness.charm.on.install.emit()

        patched_push.assert_has_calls(
            calls=[
                call(
                    Path("/etc/fluent/config.d/general.conf"),
                    test_fluentd_configs[0],
                    permissions=0o666,
                ),
                call(
                    Path("/etc/fluent/config.d/system.conf"),
                    test_fluentd_configs[1],
                    permissions=0o666,
                ),
                call(
                    Path("/etc/fluent/config.d/forward-input.conf"),
                    expected_rendered_test_forward_input_conf,
                    permissions=0o666,
                ),
            ]
        )

    def test_given_relations_not_created_when_pebble_ready_then_status_is_blocked(self):
        event = Mock()

        self.harness.charm.on.fluentd_pebble_ready.emit(event)

        assert self.harness.charm.unit.status == BlockedStatus(
            "Waiting for relation(s) to be created: fluentd-certs, replicas"
        )

    def test_given_replicas_relation_created_but_fluentd_certs_relation_not_created_when_pebble_ready_then_status_is_blocked(  # noqa: E501
        self,
    ):
        event = Mock()
        self._create_peer_relation_with_certificates(domain_config=TEST_DOMAIN)

        self.harness.charm.on.fluentd_pebble_ready.emit(event)

        assert self.harness.charm.unit.status == BlockedStatus(
            "Waiting for relation(s) to be created: fluentd-certs"
        )

    def test_given_fluentd_certs_relation_created_but_replicas_relation_not_created_when_pebble_ready_then_status_is_blocked(  # noqa: E501
        self,
    ):
        event = Mock()
        self._create_fluentd_certs_relation()

        self.harness.charm.on.fluentd_pebble_ready.emit(event)

        assert self.harness.charm.unit.status == BlockedStatus(
            "Waiting for relation(s) to be created: replicas"
        )

    def test_given_fluentd_certs_relation_created_but_fluentd_certs_not_in_the_peer_relation_data_when_pebble_ready_then_status_is_waiting(  # noqa: E501
        self,
    ):
        event = Mock()
        self._create_peer_relation_with_certificates(domain_config=TEST_DOMAIN)
        self._create_fluentd_certs_relation()

        self.harness.charm.on.fluentd_pebble_ready.emit(event)

        assert self.harness.charm.unit.status == WaitingStatus(
            "Waiting for Fluentd certificates to be available"
        )

    @patch("ops.model.Container.push")
    def test_given_fluentd_certs_relation_created_and_fluentd_certs_in_the_peer_relation_data_when_pebble_ready_then_certs_are_pushed_to_the_workload_container(  # noqa: E501
        self, patched_push
    ):
        event = Mock()
        _, peer_relation_data = self._create_peer_relation_with_certificates(
            domain_config=TEST_DOMAIN,
            fluentd_private_key=True,
            fluentd_csr=True,
            fluentd_certificate=True,
        )
        self._create_fluentd_certs_relation()

        self.harness.charm.on.fluentd_pebble_ready.emit(event)
        write_calls = patched_push.mock_calls

        self.assertEqual(
            write_calls[0],
            call(
                Path("/certs/fluentd.key"),
                peer_relation_data["fluentd_private_key"],
                permissions=0o420,
            ),
        )
        self.assertEqual(
            write_calls[1],
            call(
                Path("/certs/fluentd.csr"),
                peer_relation_data["fluentd_csr"],
                permissions=0o420,
            ),
        )
        self.assertEqual(
            write_calls[2],
            call(
                Path("/certs/fluentd.pem"),
                peer_relation_data["fluentd_cert"],
                permissions=0o420,
            ),
        )
        self.assertEqual(
            write_calls[3],
            call(
                Path("/certs/ca.pem"),
                peer_relation_data["ca_cert"],
                permissions=0o420,
            ),
        )

    @patch("ops.model.Container.push", Mock())
    def test_given_fluentd_certs_relation_created_and_fluentd_certs_in_the_peer_relation_data_when_pebble_ready_then_status_is_active(  # noqa: E501
        self,
    ):
        event = Mock()
        self._create_peer_relation_with_certificates(
            domain_config=TEST_DOMAIN,
            fluentd_private_key=True,
            fluentd_csr=True,
            fluentd_certificate=True,
        )
        self._create_fluentd_certs_relation()

        self.harness.charm.on.fluentd_pebble_ready.emit(event)

        assert self.harness.charm.unit.status == ActiveStatus()

    def test_given_peer_relation_not_created_when_fluentd_certs_relation_joined_then_status_is_waiting(  # noqa: E501
        self,
    ):
        self.harness.set_leader(is_leader=True)

        self._create_fluentd_certs_relation()

        assert self.harness.charm.unit.status == WaitingStatus(
            "Waiting for replicas relation to be created"
        )

    def test_given_peer_relation_created_and_fluentd_certs_not_in_peer_relation_data_but_fluentd_private_key_not_in_peer_relation_data_when_fluentd_certs_relation_joined_then_status_is_waiting(  # noqa: E501
        self,
    ):
        self.harness.set_leader(is_leader=True)
        self._create_peer_relation_with_certificates(domain_config=TEST_DOMAIN)

        self._create_fluentd_certs_relation()

        assert self.harness.charm.unit.status == WaitingStatus(
            "Waiting for Fluentd private key to be created"
        )

    @patch("charm.generate_csr")
    def test_given_peer_relation_created_and_fluentd_certs_not_in_peer_relation_data_and_fluentd_private_key_in_peer_relation_data_when_fluentd_certs_relation_joined_then_csr_is_generated_and_stored_in_peer_relation_data(  # noqa: E501
        self, patched_generate_csr
    ):
        self.harness.set_leader(is_leader=True)
        config = {"domain": TEST_DOMAIN}
        test_csr = b"whatever"
        patched_generate_csr.return_value = test_csr
        self.harness.update_config(key_values=config)
        peer_relation_id, relation_data = self._create_peer_relation_with_certificates(
            domain_config=TEST_DOMAIN,
            fluentd_private_key=True,
        )

        self._create_fluentd_certs_relation()

        patched_generate_csr.assert_called_once_with(
            private_key=relation_data["fluentd_private_key"].encode(),
            subject=f"fluentd.{TEST_DOMAIN}",
        )
        self.assertEqual(
            self.harness.get_relation_data(peer_relation_id, self.harness.charm.app.name)[
                "fluentd_csr"
            ],
            test_csr.decode(),
        )

    @patch(f"{TLS_CERTIFICATES_LIB}.TLSCertificatesRequiresV1.request_certificate_creation")
    @patch("charm.generate_csr")
    def test_given_peer_relation_created_and_fluentd_certs_not_in_peer_relation_data_and_fluentd_private_key_in_peer_relation_data_when_fluentd_certs_relation_joined_then_fluentd_certs_are_requested(  # noqa: E501
        self, patched_generate_csr, patched_request_certificate_creation
    ):
        self.harness.set_leader(is_leader=True)
        test_csr = b"whatever"
        patched_generate_csr.return_value = test_csr
        self._create_peer_relation_with_certificates(
            domain_config=TEST_DOMAIN,
            fluentd_private_key=True,
        )

        self._create_fluentd_certs_relation()

        patched_request_certificate_creation.assert_called_once_with(test_csr)

    @patch(f"{TLS_CERTIFICATES_LIB}.TLSCertificatesRequiresV1.request_certificate_creation")
    def test_given_peer_relation_created_and_fluentd_certs_in_peer_relation_data_when_fluentd_certs_relation_joined_then_fluentd_certs_are_not_requested(  # noqa: E501
        self, patched_request_certificate_creation
    ):
        self.harness.set_leader(is_leader=True)
        self._create_peer_relation_with_certificates(
            domain_config=TEST_DOMAIN,
            fluentd_private_key=True,
            fluentd_csr=True,
            fluentd_certificate=True,
        )

        self._create_fluentd_certs_relation()

        patched_request_certificate_creation.assert_not_called()

    @patch(f"{TLS_CERTIFICATES_LIB}.TLSCertificatesRequiresV1.request_certificate_creation")
    def test_given_peer_relation_created_and_fluentd_certs_in_peer_relation_data_but_unit_is_not_leader_when_fluentd_certs_relation_joined_then_fluentd_certs_are_not_requested(  # noqa: E501
        self, patched_request_certificate_creation
    ):
        self._create_peer_relation_with_certificates(
            domain_config=TEST_DOMAIN,
            fluentd_private_key=True,
            fluentd_csr=True,
            fluentd_certificate=True,
        )

        self._create_fluentd_certs_relation()

        patched_request_certificate_creation.assert_not_called()

    def test_given_domain_not_configured_when_config_changed_then_status_is_blocked(self):
        self.harness.update_config(key_values={"domain": ""})

        assert self.harness.charm.unit.status == BlockedStatus("Config 'domain' is not valid")

    def test_given_invalid_domain_config_when_config_then_status_is_blocked(self):
        invalid_domain = "that's invalid"
        config = {"domain": invalid_domain}

        self.harness.update_config(key_values=config)

        assert self.harness.charm.unit.status == BlockedStatus("Config 'domain' is not valid")

    def test_given_elasticsearch_url_not_configured_when_config_changed_then_status_is_blocked(
        self,
    ):
        config = {"domain": TEST_DOMAIN, "elasticsearch-url": ""}

        self.harness.update_config(key_values=config)

        assert self.harness.charm.unit.status == BlockedStatus(
            "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
        )

    def test_given_invalid_elasticsearch_url_when_config_changed_then_status_is_blocked(self):
        invalid_elasticsearch_url = "this is wrong"
        config = {
            "domain": TEST_DOMAIN,
            "elasticsearch-url": invalid_elasticsearch_url,
        }

        self.harness.update_config(key_values=config)

        assert self.harness.charm.unit.status == BlockedStatus(
            "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
        )

    def test_given_replicas_relation_created_but_fluentd_certs_relation_not_created_when_config_changed_then_status_is_blocked(  # noqa: E501
        self,
    ):
        self.harness.add_relation(relation_name="replicas", remote_app=self.harness.charm.app.name)

        self.harness.update_config(key_values=VALID_TEST_CHARM_CONFIG)

        assert self.harness.charm.unit.status == BlockedStatus(
            "Waiting for relation(s) to be created: fluentd-certs"
        )

    @patch(f"{TLS_CERTIFICATES_LIB}.TLSCertificatesRequiresV1.request_certificate_renewal")
    @patch("ops.model.Container.push", Mock())
    def test_given_unit_is_leader_and_charm_config_is_correct_and_relations_are_created_and_stored_csr_matches_charm_config_when_config_changed_then_fluentd_certs_are_not_renewed(  # noqa: E501
        self, patched_request_certificate_renewal
    ):
        self.harness.set_leader(is_leader=True)
        self._create_fluentd_certs_relation()
        self._create_peer_relation_with_certificates(
            domain_config=TEST_DOMAIN,
            fluentd_private_key=True,
            fluentd_csr=True,
        )

        self.harness.update_config(key_values=VALID_TEST_CHARM_CONFIG)

        patched_request_certificate_renewal.assert_not_called()

    @patch("charm.generate_csr")
    @patch(f"{TLS_CERTIFICATES_LIB}.TLSCertificatesRequiresV1.request_certificate_renewal")
    @patch("ops.model.Container.push", Mock())
    def test_given_unit_is_leader_and_charm_config_is_correct_and_relations_are_created_and_stored_csr_doesnt_match_charm_config_when_config_changed_then_fluentd_certs_are_renewed(  # noqa: E501
        self, patched_request_certificate_renewal, patched_generate_csr
    ):
        new_test_csr = b"whatever"
        self.harness.set_leader(is_leader=True)
        patched_generate_csr.return_value = new_test_csr
        self._create_fluentd_certs_relation()
        _, peer_relation_data = self._create_peer_relation_with_certificates(
            domain_config=TEST_DOMAIN,
            fluentd_private_key=True,
            fluentd_csr=True,
        )
        old_csr = peer_relation_data["fluentd_csr"]

        self.harness.update_config(key_values={"domain": "new-domain.com"})

        patched_request_certificate_renewal.assert_called_once_with(
            old_certificate_signing_request=old_csr.encode(),
            new_certificate_signing_request=new_test_csr,
        )

    @patch(f"{TLS_CERTIFICATES_LIB}.TLSCertificatesRequiresV1.request_certificate_renewal")
    @patch("ops.model.Container.push", Mock())
    def test_given_unit_is_not_leader_and_charm_config_is_correct_and_relations_are_created_and_stored_csr_doesnt_match_charm_config_when_config_changed_then_fluentd_certs_are_not_renewed(  # noqa: E501
        self, patched_request_certificate_renewal
    ):
        self._create_fluentd_certs_relation()
        self._create_peer_relation_with_certificates(
            domain_config=TEST_DOMAIN,
            fluentd_private_key=True,
            fluentd_csr=True,
        )

        self.harness.update_config(key_values={"domain": "new-domain.com"})

        patched_request_certificate_renewal.assert_not_called()

    def test_charm_config_is_correct_and_relations_are_created_but_fluentd_csr_is_not_available_when_config_changed_then_status_is_waiting(  # noqa: E501
        self,
    ):
        self._create_fluentd_certs_relation()
        self._create_peer_relation_with_certificates(fluentd_private_key=True)

        self.harness.update_config(key_values={})

        assert self.harness.charm.unit.status == WaitingStatus(
            "Waiting for Fluentd CSR to be available"
        )

    def test_charm_config_is_correct_and_relations_are_created_but_fluentd_certs_not_available_when_config_changed_then_status_is_waiting(  # noqa: E501
        self,
    ):
        self._create_fluentd_certs_relation()
        self._create_peer_relation_with_certificates(
            fluentd_private_key=True,
            fluentd_csr=True,
        )

        self.harness.update_config(key_values={})

        assert self.harness.charm.unit.status == WaitingStatus(
            "Waiting for Fluentd certificates to be available"
        )

    @patch("ops.model.Container.push")
    def test_charm_config_is_correct_and_relations_are_created_and_fluentd_certs_available_when_config_changed_then_certs_are_stored_in_the_container(  # noqa: E501
        self, patched_push
    ):
        self._create_fluentd_certs_relation()
        _, peer_relation_data = self._create_peer_relation_with_certificates(
            fluentd_private_key=True,
            fluentd_csr=True,
            fluentd_certificate=True,
        )

        self.harness.update_config(key_values={})
        write_calls = patched_push.mock_calls

        self.assertEqual(
            write_calls[0],
            call(
                Path("/certs/fluentd.key"),
                peer_relation_data["fluentd_private_key"],
                permissions=0o420,
            ),
        )
        self.assertEqual(
            write_calls[1],
            call(
                Path("/certs/fluentd.csr"),
                peer_relation_data["fluentd_csr"],
                permissions=0o420,
            ),
        )
        self.assertEqual(
            write_calls[2],
            call(
                Path("/certs/fluentd.pem"),
                peer_relation_data["fluentd_cert"],
                permissions=0o420,
            ),
        )
        self.assertEqual(
            write_calls[3],
            call(
                Path("/certs/ca.pem"),
                peer_relation_data["ca_cert"],
                permissions=0o420,
            ),
        )

    @patch("ops.model.Container.push")
    @patch("builtins.open", new_callable=mock_open, read_data=TEST_OUTPUT_CONF_TEMPLATE)
    def test_given_fluentd_certificates_in_peer_relation_data_when_config_changed_then_output_conf_is_generated_and_stored_in_the_container(  # noqa: E501
        self, _, patched_push
    ):
        expected_rendered_test_output_conf = f"""{TEST_ES_URL.split(":")[0]}
{TEST_ES_URL.split(":")[1]}
{TEST_FLUENTD_CHUNK_LIMIT}
{TEST_FLUENTD_QUEUE_LIMIT}"""
        self._create_peer_relation_with_certificates(
            domain_config=TEST_DOMAIN,
            fluentd_private_key=True,
            fluentd_csr=True,
            fluentd_certificate=True,
        )
        self._create_fluentd_certs_relation()

        self.harness.update_config(key_values=VALID_TEST_CHARM_CONFIG)
        write_calls = patched_push.mock_calls

        self.assertEqual(
            write_calls[4],
            call(
                Path("/etc/fluent/config.d/output.conf"),
                expected_rendered_test_output_conf,
                permissions=0o666,
            ),
        )

    @patch("ops.model.Container.push", Mock())
    def test_given_config_is_valid__and_configs_are_stored_when_pebble_ready_then_plan_is_filled_with_fluentd_service_content(  # noqa: E501
        self,
    ):
        self._create_peer_relation_with_certificates(
            domain_config=TEST_DOMAIN,
            fluentd_private_key=True,
            fluentd_csr=True,
            fluentd_certificate=True,
        )
        self._create_fluentd_certs_relation()

        self.harness.update_config(key_values=VALID_TEST_CHARM_CONFIG)

        expected_plan = {
            "services": {
                "fluentd": {
                    "override": "replace",
                    "summary": "fluentd",
                    "startup": "enabled",
                    "command": "./run.sh",
                }
            },
        }

        updated_plan = self.harness.get_container_pebble_plan("fluentd").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    @patch("ops.model.Container.push", Mock())
    def test_given_config_is_valid_and_configs_are_stored_when_pebble_ready_then_status_is_active(
        self,
    ):
        self._create_peer_relation_with_certificates(
            domain_config=TEST_DOMAIN,
            fluentd_private_key=True,
            fluentd_csr=True,
            fluentd_certificate=True,
        )
        self._create_fluentd_certs_relation()

        self.harness.update_config(key_values=VALID_TEST_CHARM_CONFIG)

        assert self.harness.charm.unit.status == ActiveStatus()

    @patch("ops.model.Container.push", Mock())
    def test_given_fluentd_certs_relation_created_when_certificates_available_then_fluentd_certs_are_stored_in_peer_relation_data(  # noqa: E501
        self,
    ):
        test_fluentd_cert = "whatever cert"
        test_ca_cert = "whatevent ca cert"
        self.harness.set_leader(is_leader=True)
        self._create_fluentd_certs_relation()
        peer_relation_id, peer_relation_data = self._create_peer_relation_with_certificates(
            domain_config=TEST_DOMAIN,
            fluentd_private_key=True,
            fluentd_csr=True,
        )

        self.harness.charm._fluentd_certificates.on.certificate_available.emit(
            certificate_signing_request="some csr",
            certificate=test_fluentd_cert,
            ca=test_ca_cert,
            chain="some chain",
        )
        peer_relation_data = self.harness.get_relation_data(
            peer_relation_id, self.harness.charm.app.name
        )

        self.assertEqual(peer_relation_data["fluentd_cert"], test_fluentd_cert)
        self.assertEqual(peer_relation_data["ca_cert"], test_ca_cert)

    @patch(f"{TLS_CERTIFICATES_LIB}.TLSCertificatesRequiresV1.request_certificate_renewal")
    @patch("charm.generate_csr")
    @patch("ops.model.Container.push", Mock())
    def test_given_unit_is_leader_when_certificate_expiring_then_certificate_renewal_is_requested(
        self, patched_generate_csr, patched_request_certificate_renewal
    ):
        test_csr = b"newcsr"
        patched_generate_csr.return_value = test_csr
        self.harness.set_leader(is_leader=True)
        _, peer_relation_data = self._create_peer_relation_with_certificates(
            domain_config=TEST_DOMAIN,
            fluentd_private_key=True,
            fluentd_csr=True,
            fluentd_certificate=True,
        )
        old_csr = peer_relation_data["fluentd_csr"]
        self._create_fluentd_certs_relation()
        self.harness.update_config(key_values=VALID_TEST_CHARM_CONFIG)

        self.harness.charm._fluentd_certificates.on.certificate_expiring.emit(
            certificate="certificate",
            expiry="expiry",
        )

        patched_request_certificate_renewal.assert_called_once_with(
            old_certificate_signing_request=old_csr.encode(),
            new_certificate_signing_request=test_csr,
        )

    @patch(f"{TLS_CERTIFICATES_LIB}.TLSCertificatesRequiresV1.request_certificate_renewal")
    @patch("charm.generate_csr")
    @patch("ops.model.Container.push", Mock())
    def test_given_unit_is_leader_when_certificate_expired_then_certificate_renewal_is_requested(
        self, patched_generate_csr, patched_request_certificate_renewal
    ):
        test_csr = b"newcsr"
        patched_generate_csr.return_value = test_csr
        self.harness.set_leader(is_leader=True)
        _, peer_relation_data = self._create_peer_relation_with_certificates(
            domain_config=TEST_DOMAIN,
            fluentd_private_key=True,
            fluentd_csr=True,
            fluentd_certificate=True,
        )
        old_csr = peer_relation_data["fluentd_csr"]
        self._create_fluentd_certs_relation()
        self.harness.update_config(key_values=VALID_TEST_CHARM_CONFIG)

        self.harness.charm._fluentd_certificates.on.certificate_expired.emit(
            certificate="certificate",
        )

        patched_request_certificate_renewal.assert_called_once_with(
            old_certificate_signing_request=old_csr.encode(),
            new_certificate_signing_request=test_csr,
        )

    @patch(f"{TLS_CERTIFICATES_LIB}.TLSCertificatesRequiresV1.request_certificate_renewal")
    @patch("charm.generate_csr")
    @patch("ops.model.Container.push", Mock())
    def test_given_unit_is_leader_when_certificate_revoked_then_certificate_renewal_is_requested(
        self, patched_generate_csr, patched_request_certificate_renewal
    ):
        test_csr = b"newcsr"
        patched_generate_csr.return_value = test_csr
        self.harness.set_leader(is_leader=True)
        _, peer_relation_data = self._create_peer_relation_with_certificates(
            domain_config=TEST_DOMAIN,
            fluentd_private_key=True,
            fluentd_csr=True,
            fluentd_certificate=True,
        )
        old_csr = peer_relation_data["fluentd_csr"]
        self._create_fluentd_certs_relation()
        self.harness.update_config(key_values=VALID_TEST_CHARM_CONFIG)

        self.harness.charm._fluentd_certificates.on.certificate_revoked.emit(
            certificate_signing_request="some csr",
            certificate="certificate",
            ca="ca",
            chain="some chain",
            revoked=True,
        )

        patched_request_certificate_renewal.assert_called_once_with(
            old_certificate_signing_request=old_csr.encode(),
            new_certificate_signing_request=test_csr,
        )

    def _create_empty_relations(self) -> Tuple[int, int]:
        """Creates empty replicas and fluentd-certs relations and returns relation ids.

        Returns:
            Tuple[int, int]: Relation ids
        """
        peer_relation_id = self.harness.add_relation(
            relation_name="replicas", remote_app=self.harness.charm.app.name
        )
        self.harness.add_relation_unit(peer_relation_id, self.harness.charm.app.name)
        fluentd_certs_relation_id = self.harness.add_relation(
            relation_name="fluentd-certs", remote_app="provider"
        )
        self.harness.add_relation_unit(fluentd_certs_relation_id, "provider/0")

        return peer_relation_id, fluentd_certs_relation_id

    def _create_fluentd_certs_relation(self) -> int:
        """Creates fluentd-certs relation and returns its id.

        Returns:
            int: Relation id
        """
        fluentd_certs_relation_id = self.harness.add_relation(
            relation_name="fluentd-certs", remote_app="provider"
        )
        self.harness.add_relation_unit(fluentd_certs_relation_id, "provider/0")
        return fluentd_certs_relation_id

    def _create_peer_relation_with_certificates(
        self,
        domain_config: str = "",
        fluentd_private_key: bool = False,
        fluentd_csr: bool = False,
        fluentd_certificate: bool = False,
    ) -> Tuple[int, dict]:
        """Creates a peer relation and adds certificates in its data.

        Args:
            domain_config: Domain config
            fluentd_private_key: Set Fluentd private key
            fluentd_csr: Set Fluentd CSR
            fluentd_certificate: Set Fluentd certificate

        Returns:
            int: Peer relation ID
            dict: Relation data
        """
        key_values = {}

        if fluentd_private_key:
            key_values["fluentd_private_key"] = generate_private_key().decode().strip()

        if fluentd_csr:
            if not fluentd_private_key:
                raise ValueError("fluentd_private_key must be True if fluentd_csr is True")
            key_values["fluentd_csr"] = (
                generate_csr(
                    private_key=key_values["fluentd_private_key"].encode(),
                    subject=f"fluentd.{domain_config}",
                )
                .decode()
                .strip()
            )
        if fluentd_certificate:
            if not fluentd_csr:
                raise ValueError("fluentd_csr must be True if fluentd_certificate is True")
            ca_private_key = generate_private_key()
            ca_certificate = generate_ca(private_key=ca_private_key, subject="whatever")
            key_values["ca_cert"] = ca_certificate.decode().strip()
            key_values["fluentd_cert"] = (
                generate_certificate(
                    ca=ca_certificate,
                    ca_key=ca_private_key,
                    csr=key_values["fluentd_csr"].encode(),
                )
                .decode()
                .strip()
            ) + "\n"

        peer_relation_id = self.harness.add_relation("replicas", self.harness.charm.app.name)
        self.harness.add_relation_unit(peer_relation_id, self.harness.charm.unit.name)

        self.harness.update_relation_data(
            relation_id=peer_relation_id,
            app_or_unit=self.harness.charm.app.name,
            key_values=key_values,
        )
        return peer_relation_id, key_values
