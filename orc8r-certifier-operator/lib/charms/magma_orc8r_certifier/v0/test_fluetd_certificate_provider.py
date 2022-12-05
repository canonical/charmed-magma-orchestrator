# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest

from unittest.mock import PropertyMock, call, patch
from ops import testing
from test_charms.test_fluentd_provider.src.charm import (
    DummyProviderCharm
)

TEST_CERTIFICATE = "dummy cert"
TEST_CERTIFICATE_SIGNING_REQUEST = "dummy csr"


class TestFluentdCertificateProvider(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = testing.Harness(DummyProviderCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.relationship_name = "cert-fluentd"
    
    def test_given_fluentd_csr_created_when_cert_fluentd_relation_joined_then_csr_is_in_relation_data(
        self, patch_push
    ):
        pass

    def test_given_fluentd_certificate_in_relation_data_when_certificate_available_event_then_certificate_is_pushed_to_container(
        self
    ):
        pass