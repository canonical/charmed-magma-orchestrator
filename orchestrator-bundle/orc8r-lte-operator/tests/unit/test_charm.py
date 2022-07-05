#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import call, patch

from ops import testing

from charm import MagmaOrc8rLteCharm

testing.SIMULATE_CAN_CONNECT = True


class Test(unittest.TestCase):
    """
    Unit tests for charms that leverage the `orc8r_base` and `orc8r_base_db` libraries are
    done at the library level. This file only contains tests for additional functionality not
    present in the base libraries.
    """

    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports, additional_labels, additional_annotations: None,
    )
    def setUp(self):
        self.harness = testing.Harness(MagmaOrc8rLteCharm)
        self.harness.set_can_connect("magma-orc8r-lte", True)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch("ops.model.Container.push")
    def test_given_new_charm_when_on_install_event_then_config_files_are_created(self, patch_push):
        self.harness.charm.on.install.emit()

        calls = [
            call(
                "/var/opt/magma/configs/orc8r/metricsd.yml",
                'prometheusQueryAddress: "http://orc8r-prometheus:9090"\n'
                'alertmanagerApiURL: "http://orc8r-alertmanager:9093/api/v2"\n'
                '"profile": "prometheus"\n',
            ),
            call(
                "/var/opt/magma/configs/orc8r/analytics.yml",
                '"appID": ""\n'
                '"appSecret": ""\n'
                '"categoryName": "magma"\n'
                '"exportMetrics": false\n'
                '"metricExportURL": ""\n'
                '"metricsPrefix": ""\n',
            ),
        ]
        patch_push.assert_has_calls(calls)
