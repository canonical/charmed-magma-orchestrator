#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, call, patch

from ops import testing

from charm import MagmaOrc8rEventdCharm

testing.SIMULATE_CAN_CONNECT = True


class Test(unittest.TestCase):
    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports, additional_labels, additional_annotations: None,
    )
    def setUp(self):
        self.harness = testing.Harness(MagmaOrc8rEventdCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch("ops.model.Container.push")
    def test_given_new_charm_when_on_install_event_then_config_files_are_created(self, patch_push):
        event = Mock()

        self.harness.charm._on_install(event)

        calls = [
            call(
                "/var/opt/magma/configs/orc8r/elastic.yml",
                '"elasticHost": "orc8r-elasticsearch"\n' '"elasticPort": 80\n',
            ),
        ]
        patch_push.assert_has_calls(calls)
