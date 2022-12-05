# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest

from unittest.mock import PropertyMock, call, patch
from ops import testing
from test_charms.test_fluentd_requirer.src.charm import (
    DummyRequirerCharm
)

TEST_CERTIFICATE = "dummy cert"
TEST_CERT_PATH = "dummy cert path"
TEST_CERTIFICATE_SIGNING_REQUEST = "dummy csr"


class TestFluentdCertificateRequirer(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = testing.Harness(DummyRequirerCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.relationship_name = "cert-fluentd"
    
    @patch("ops.model.Container.push")
    def test_given_fluentd_csr_created_when_cert_fluentd_relation_joined_then_csr_is_in_relation_data(
        self, patch_push
    ):
        relation_id = self.harness.add_relation(
            relation_name=self.relationship_name, remote_app="fluentd-certificate-provider"
        )
        self.harness.add_relation_unit(
            relation_id=relation_id, remote_unit_name="fluentd-certificate-provider/0"
        )
        
        relation_data = self.harness.get_relation_data(
             relation_id=relation_id, app_or_unit=self.harness.charm.unit.name
         )
        self.assertEqual(TEST_CERTIFICATE_SIGNING_REQUEST, relation_data["certificate-signing-request"])
    
    
    # TODO: not working
    @patch("ops.model.Container.push")
    def test_given_fluentd_certificate_in_relation_data_when_certificate_available_event_then_certificate_is_pushed_to_container(
        self, patch_push
    ):
        relation_id = self.harness.add_relation(
            relation_name=self.relationship_name, remote_app="fluentd-certificate-provider"
        )
        self.harness.add_relation_unit(
            relation_id=relation_id, remote_unit_name="fluentd-certificate-provider/0"
        )
        self.harness.update_relation_data(
            relation_id=relation_id,
            app_or_unit="fluentd-certificate-provider/0",
            key_values={"certificate": TEST_CERTIFICATE},
        )
        self.harness.charm.on.fluentd_certificate_available.emit()
        
        self.harness.charm.unit.get_container("dummy-container").push.assert_called_once_with(
            TEST_CERT_PATH, TEST_CERTIFICATE
        )