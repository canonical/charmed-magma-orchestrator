#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import call, patch

from ops import testing
from ops.model import BlockedStatus

from charm import MagmaOrc8rEventdCharm


class Test(unittest.TestCase):
    """Placeholder tests.

    Unit tests for charms that leverage the `orc8r_base` and `orc8r_base_db` libraries are
    done at the library level. This file only contains tests for additional functionality not
    present in the base libraries.
    """

    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports, additional_labels, additional_annotations: None,
    )
    def setUp(self):
        self.harness = testing.Harness(MagmaOrc8rEventdCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_given_default_config_when_on_config_changed_then_status_is_blocked(self):
        key_values = {"elasticsearch-url": ""}
        self.harness.container_pebble_ready("magma-orc8r-eventd")

        self.harness.update_config(key_values=key_values)

        assert self.harness.charm.unit.status == BlockedStatus(
            "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
        )

    @patch("ops.model.Container.push")
    def test_given_good_elasticsearch_config_when_config_changed_then_config_is_written_to_file(
        self, patch_push
    ):
        hostname = "blablabla"
        port = 80
        config = {"elasticsearch-url": f"{hostname}:{port}"}

        self.harness.container_pebble_ready("magma-orc8r-eventd")
        self.harness.update_config(key_values=config)

        calls = [
            call(
                "/var/opt/magma/configs/orc8r/elastic.yml",
                f'"elasticHost": "{hostname}"\n' f'"elasticPort": {port}\n',
            ),
        ]
        patch_push.assert_has_calls(calls)

    def test_given_bad_elasticsearch_config_when_config_changed_then_status_is_blocked(self):
        config = {"elasticsearch-url": "hello"}

        self.harness.container_pebble_ready("magma-orc8r-eventd")
        self.harness.update_config(key_values=config)

        assert self.harness.charm.unit.status == BlockedStatus(
            "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
        )
