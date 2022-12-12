# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from pathlib import Path
from typing import Mapping, Union
from unittest.mock import Mock, call, mock_open, patch

from ops import testing
from ops.model import ActiveStatus, BlockedStatus

from charm import FluentdElasticsearchCharm

testing.SIMULATE_CAN_CONNECT = True

TEST_ES_URL = "testes:1234"
TEST_FLUENTD_CHUNK_LIMIT = "size"
TEST_FLUENTD_QUEUE_LIMIT = 4321
VALID_TEST_CHARM_CONFIG: Mapping[str, Union[str, int]] = {
    "elasticsearch-url": TEST_ES_URL,
    "fluentd-chunk-limit-size": TEST_FLUENTD_CHUNK_LIMIT,
    "fluentd-queue-limit-length": TEST_FLUENTD_QUEUE_LIMIT,
}
TEST_OUTPUT_CONF_TEMPLATE = b"""{{ elasticsearch_host }}
{{ elasticsearch_port }}
{{ fluentd_chunk_limit_size }}
{{ fluentd_queue_limit_length }}
"""


class TestCharm(unittest.TestCase):
    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports, service_type: None,
    )
    def setUp(self):
        self.harness = testing.Harness(FluentdElasticsearchCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.harness.container_pebble_ready(container_name="fluentd")

    @patch("ops.model.Container.push")
    @patch("builtins.open", new_callable=mock_open())
    def test_given_fluentd_charm_when_install_then_static_configs_are_pushed_to_the_container(
        self, patched_open, patched_push
    ):
        test_fluentd_configs = [
            "config one",
            "config two",
            "config three",
        ]
        patched_open.side_effect = [
            mock_open(read_data=content).return_value for content in test_fluentd_configs
        ]

        self.harness.charm.on.install.emit()

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
            ]
        )

    def test_given_invalid_elasticsearch_url_when_pebble_ready_then_status_is_blocked(self):
        invalid_elasticsearch_url = "this is wrong"
        config = {
            "elasticsearch-url": invalid_elasticsearch_url,
        }
        self.harness.update_config(key_values=config)

        assert self.harness.charm.unit.status == BlockedStatus(
            "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
        )

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.push")
    @patch("builtins.open", new_callable=mock_open, read_data=TEST_OUTPUT_CONF_TEMPLATE)
    def test_given_config_is_valid_when_pebble_ready_then_fluentd_configs_are_pushed_to_the_container(  # noqa: E501
        self, _, patched_push, patched_exists
    ):
        patched_exists.return_value = True

        self.harness.update_config(key_values=VALID_TEST_CHARM_CONFIG)
        expected_rendered_test_optput_conf = f"""{TEST_ES_URL.split(":")[0]}
{TEST_ES_URL.split(":")[1]}
{TEST_FLUENTD_CHUNK_LIMIT}
{TEST_FLUENTD_QUEUE_LIMIT}"""

        patched_push.assert_called_once_with(
            Path("/etc/fluent/config.d/output.conf"),
            expected_rendered_test_optput_conf,
            permissions=511,
        )

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.push", Mock())
    def test_given_config_is_valid__and_configs_are_stored_when_pebble_ready_then_plan_is_filled_with_fluentd_service_content(  # noqa: E501
        self, patched_exists
    ):
        patched_exists.return_value = True
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

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.push", Mock())
    def test_given_config_is_valid_and_configs_are_stored_when_pebble_ready_then_status_is_active(
        self, patched_exists
    ):
        patched_exists.return_value = True

        self.harness.update_config(key_values=VALID_TEST_CHARM_CONFIG)

        assert self.harness.charm.unit.status == ActiveStatus()