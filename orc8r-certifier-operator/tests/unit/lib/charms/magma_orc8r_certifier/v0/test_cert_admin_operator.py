# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest

from ops import testing
from test_charms.test_admin_operator_provider.src.charm import (  # type: ignore[import]
    WhateverCharm,
)


class TestCertAdminOperatorProvides(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = testing.Harness(WhateverCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.relationship_name = "cert-admin-operator"

    def test_given_magmalte_relation_relation_when_set_certificate_then_certificate_is_added_to_relation_data(  # noqa: E501
        self,
    ):
        certificate = "whatever cert"
        private_key = "whatever private key"
        relation_id = self.harness.add_relation(
            relation_name=self.relationship_name, remote_app="whatever app"
        )

        self.harness.charm.admin_operator.set_certificate(
            certificate=certificate, private_key=private_key, relation_id=relation_id
        )

        relation_data = self.harness.get_relation_data(
            relation_id=relation_id, app_or_unit=self.harness.charm.unit.name
        )
        self.assertEqual(certificate, relation_data["certificate"])
