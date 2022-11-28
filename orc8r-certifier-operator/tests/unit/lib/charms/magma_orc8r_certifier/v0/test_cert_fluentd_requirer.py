# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import PropertyMock, call, patch

from ops import testing
from test_charms.test_fluentd_requirer.src.charm import (  # type: ignore[import]
    WhateverCharm,
)

TEST_CERTIFICATE = "whatever cert"
TEST_PRIVATE_KEY = "some private key"
TEST_CERT_PATH = "whatever"
TEST_PRIVATE_KEY_PATH = "/some/path"


class TestCertRootRequires(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = testing.Harness(WhateverCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.relationship_name = "cert-fluentd"

    @patch(
        "test_charms.test_fluentd_requirer.src.charm.WhateverCharm.CERT_PATH",
        new_callable=PropertyMock,
    )
    @patch(
        "test_charms.test_fluentd_requirer.src.charm.WhateverCharm.PRIVATE_KEY_PATH",
        new_callable=PropertyMock,
    )
    @patch("ops.model.Container.push")
    def test_given_test_rootca_requirer_charm_when_certificate_available_then_certificate_is_pushed_to_the_container(  # noqa: E501
        self, patched_pushed, patched_private_key_path, patched_cert_path
    ):
        patched_cert_path.return_value = TEST_CERT_PATH
        patched_private_key_path.return_value = TEST_PRIVATE_KEY_PATH
        expected_push_calls = [
            call(TEST_CERT_PATH, TEST_CERTIFICATE),
            call(TEST_PRIVATE_KEY_PATH, TEST_PRIVATE_KEY),
        ]
        relation_id = self.harness.add_relation(
            relation_name=self.relationship_name, remote_app="whatever-app"
        )
        self.harness.add_relation_unit(relation_id, "whatever-app/0")
        self.harness.update_relation_data(
            relation_id=relation_id,
            app_or_unit="whatever-app/0",
            key_values={"certificate": TEST_CERTIFICATE, "private_key": TEST_PRIVATE_KEY},
        )

        patched_pushed.assert_has_calls(expected_push_calls)
