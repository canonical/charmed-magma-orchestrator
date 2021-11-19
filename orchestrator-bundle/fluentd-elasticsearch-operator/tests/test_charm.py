# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest

from ops.model import ActiveStatus
from ops.testing import Harness

from charm import FluentdElasticsearchCharm


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(FluentdElasticsearchCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_given_initial_status_when_get_pebble_plan_then_content_is_empty(self):
        initial_plan = self.harness.get_container_pebble_plan("fluentd-elasticsearch")
        self.assertEqual(initial_plan.to_yaml(), "{}\n")

    def test_given_pebble_ready_when_get_pebble_plan_then_plan_is_filled_with_fluentd_service_content(  # noqa: E501
        self,
    ):
        expected_plan = {
            "services": {
                "fluentd_elasticsearch": {
                    "override": "replace",
                    "summary": "fluentd_elasticsearch",
                    "startup": "enabled",
                    "command": "./run.sh",
                    "environment": {
                        "OUTPUT_HOST": "bla.com",
                        "OUTPUT_PORT": 443,
                        "OUTPUT_SCHEME": "https",
                        "OUTPUT_SSL_VERSION": "TLSv1",
                        "OUTPUT_BUFFER_CHUNK_LIMIT": "2M",
                        "OUTPUT_BUFFER_QUEUE_LIMIT": 8,
                    },
                }
            },
        }
        container = self.harness.model.unit.get_container("fluentd-elasticsearch")
        self.harness.charm.on.fluentd_elasticsearch_pebble_ready.emit(container)
        updated_plan = self.harness.get_container_pebble_plan("fluentd-elasticsearch").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    def test_given_pebble_ready_when_get_status_then_status_is_active(self):
        container = self.harness.model.unit.get_container("fluentd-elasticsearch")
        self.harness.charm.on.fluentd_elasticsearch_pebble_ready.emit(container)
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())
