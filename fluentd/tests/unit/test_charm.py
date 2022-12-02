# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from pathlib import Path
from unittest.mock import Mock, call, mock_open, patch

from ops import testing
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

from charm import FluentdElasticsearchCharm

testing.SIMULATE_CAN_CONNECT = True

TEST_DOMAIN = "example.com"
TEST_ES_URL = "testes:1234"
TEST_ES_SCHEMA = "schema"
TEST_ES_SSL_VERSION = "secure"
TEST_FLUENTD_CHUNK_LIMIT = "size"
TEST_FLUENTD_QUEUE_LIMIT = "4321"
VALID_TEST_CHARM_CONFIG = {
    "domain": TEST_DOMAIN,
    "elasticsearch-url": TEST_ES_URL,
    "elasticsearch-schema": TEST_ES_SCHEMA,
    "elasticsearch-ssl-version": TEST_ES_SSL_VERSION,
    "fluentd-chunk-limit-size": TEST_FLUENTD_CHUNK_LIMIT,
    "fluentd-queue-limit-length": TEST_FLUENTD_QUEUE_LIMIT,
}


class TestCharm(unittest.TestCase):
    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports, service_type, service_name, additional_annotations: None,
    )
    def setUp(self):
        self.harness = testing.Harness(FluentdElasticsearchCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_given_domain_not_configured_when_pebble_ready_then_status_is_blocked(self):
        self.harness.container_pebble_ready(container_name="fluentd")

        assert self.harness.charm.unit.status == BlockedStatus("Config 'domain' is not valid")

    def test_given_invalid_domain_config_when_pebble_ready_then_status_is_blocked(self):
        invalid_domain = "that's invalid"
        config = {"domain": invalid_domain}
        self.harness.update_config(key_values=config)

        self.harness.container_pebble_ready(container_name="fluentd")

        assert self.harness.charm.unit.status == BlockedStatus("Config 'domain' is not valid")

    def test_given_elasticsearch_url_not_configured_when_pebble_ready_then_status_is_blocked(self):
        config = {"domain": TEST_DOMAIN}
        self.harness.update_config(key_values=config)

        self.harness.container_pebble_ready(container_name="fluentd")

        assert self.harness.charm.unit.status == BlockedStatus(
            "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
        )

    def test_given_invalid_elasticsearch_url_when_pebble_ready_then_status_is_blocked(self):
        invalid_elasticsearch_url = "this is wrong"
        config = {
            "domain": TEST_DOMAIN,
            "elasticsearch-url": invalid_elasticsearch_url,
        }
        self.harness.update_config(key_values=config)

        self.harness.container_pebble_ready(container_name="fluentd")

        assert self.harness.charm.unit.status == BlockedStatus(
            "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
        )

    def test_given_required_relations_not_created_when_pebble_ready_then_status_is_blocked(self):
        self.harness.update_config(key_values=VALID_TEST_CHARM_CONFIG)

        self.harness.container_pebble_ready(container_name="fluentd")

        assert self.harness.charm.unit.status == BlockedStatus(
            "Waiting for relation(s) to be created: cert-certifier"
        )

    def test_given_required_certs_are_not_stored_when_pebble_ready_then_status_is_waiting(self):
        self.harness.add_relation(relation_name="cert-certifier", remote_app="whatever")
        self.harness.update_config(key_values=VALID_TEST_CHARM_CONFIG)

        self.harness.container_pebble_ready(container_name="fluentd")

        assert self.harness.charm.unit.status == WaitingStatus(
            "Waiting for certificates to be available"
        )

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.push")
    @patch("builtins.open", new_callable=mock_open())
    def test_given_config_is_valid_and_relations_are_created_and_certs_are_stored_when_pebble_ready_then_fluentd_configs_are_pushed_to_the_container(  # noqa: E501
        self, patched_open, patched_push, patched_exists
    ):
        patched_exists.return_value = True
        test_output_conf_template = b"""
        {{ domain }}
        {{ elasticsearch_host }}
        {{ elasticsearch_port }}
        {{ elasticsearch_schema }}
        {{ elasticsearch_ssl_version }}
        {{ fluentd_chunk_limit_size }}
        {{ fluentd_queue_limit_length }}
        """
        test_fluentd_configs = [
            "config one",
            "config two",
            "config three",
            test_output_conf_template,
        ]
        patched_open.side_effect = [
            mock_open(read_data=content).return_value for content in test_fluentd_configs
        ]
        self.harness.add_relation(relation_name="cert-certifier", remote_app="whatever")
        self.harness.update_config(key_values=VALID_TEST_CHARM_CONFIG)
        expected_rendered_test_optput_conf = f"""
        {TEST_DOMAIN}
        {TEST_ES_URL.split(":")[0]}
        {TEST_ES_URL.split(":")[1]}
        {TEST_ES_SCHEMA}
        {TEST_ES_SSL_VERSION}
        {TEST_FLUENTD_CHUNK_LIMIT}
        {TEST_FLUENTD_QUEUE_LIMIT}
        """

        self.harness.container_pebble_ready(container_name="fluentd")

        patched_push.assert_has_calls(
            calls=[
                call(
                    Path("/etc/fluent/config.d/forward-input.conf"),
                    test_fluentd_configs[0],
                    permissions=0o777,
                ),
                call(
                    Path("/etc/fluent/config.d/general.conf"),
                    test_fluentd_configs[1],
                    permissions=0o777,
                ),
                call(
                    Path("/etc/fluent/config.d/system.conf"),
                    test_fluentd_configs[2],
                    permissions=0o777,
                ),
                call(
                    Path("/etc/fluent/config.d/output.conf"),
                    expected_rendered_test_optput_conf,
                    permissions=0o777,
                ),
            ]
        )

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.push", Mock())
    def test_given_config_is_valid_and_relations_are_created_and_certs_are_stored_and_configs_are_stored_when_pebble_ready_then_plan_is_filled_with_fluentd_service_content(  # noqa: E501
        self, patched_exists
    ):
        patched_exists.return_value = True
        self.harness.add_relation(relation_name="cert-certifier", remote_app="whatever")
        self.harness.update_config(key_values=VALID_TEST_CHARM_CONFIG)

        self.harness.container_pebble_ready(container_name="fluentd")

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

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.push", Mock())
    def test_given_config_is_valid_and_relations_are_created_and_certs_are_stored_and_configs_are_stored_when_pebble_ready_then_status_is_active(  # noqa: E501
        self, patched_exists
    ):
        patched_exists.return_value = True
        self.harness.add_relation(relation_name="cert-certifier", remote_app="whatever")
        self.harness.update_config(key_values=VALID_TEST_CHARM_CONFIG)

        self.harness.container_pebble_ready(container_name="fluentd")

        assert self.harness.charm.unit.status == ActiveStatus()
