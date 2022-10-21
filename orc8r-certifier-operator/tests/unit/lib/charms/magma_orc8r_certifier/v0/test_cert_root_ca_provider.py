# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import PropertyMock, patch

from ops import testing
from test_charms.test_root_ca_provider.src.charm import (  # type: ignore[import]
    WhateverCharm,
)


class TestCertRootProvides(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = testing.Harness(WhateverCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.relationship_name = "cert-root-ca"

    @patch(
        "test_charms.test_root_ca_provider.src.charm.WhateverCharm.TEST_CERTIFICATE",
        new_callable=PropertyMock,
    )
    def test_given_cert_root_relation_when_set_certificate_then_certificate_is_added_to_relation_data(  # noqa: E501
        self, patched_test_cert
    ):
        certificate = "whatever cert"
        patched_test_cert.return_value = certificate
        relation_id = self.harness.add_relation(
            relation_name=self.relationship_name, remote_app="whatever-app"
        )
        self.harness.add_relation_unit(relation_id, "whatever-app/0")

        relation_data = self.harness.get_relation_data(
            relation_id=relation_id, app_or_unit=self.harness.charm.unit.name
        )
        self.assertEqual(certificate, relation_data["certificate"])
