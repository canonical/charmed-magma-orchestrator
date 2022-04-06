#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, call, patch

from ops import testing

from charm import MagmaOrc8rMetricsdCharm

testing.SIMULATE_CAN_CONNECT = True


class MockModel:
    def __init__(self, name: str):
        self._name = name

    @property
    def name(self):
        return self._name


class TestCharm(unittest.TestCase):
    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports, additional_labels, additional_annotations: None,
    )
    def setUp(self):
        self.harness = testing.Harness(MagmaOrc8rMetricsdCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.maxDiff = None

    @patch("ops.model.Container.push")
    def test_given_new_charm_when_on_install_event_then_config_file_is_created(self, patch_push):
        event = Mock()

        self.harness.charm._on_install(event)

        calls = [
            call(
                "/var/opt/magma/configs/orc8r/metricsd.yml",
                'prometheusQueryAddress: "http://orc8r-prometheus:9090"\n'
                'alertmanagerApiURL: "http://orc8r-alertmanager:9093/api/v2"\n'
                'prometheusConfigServiceURL: "http://orc8r-prometheus:9100/v1"\n'
                'alertmanagerConfigServiceURL: "http://orc8r-alertmanager:9101/v1"\n'
                '"profile": "prometheus"\n',
            ),
        ]
        patch_push.assert_has_calls(calls)
