import unittest
from unittest.mock import Mock

from charms.magma_nms_magmalte.v0.admin_operator import AdminOperatorProvides


class TestAdminOperatorProvides(unittest.TestCase):

    def setUp(self) -> None:
        self.charm = Mock()
        self.relationship_name = ""
        self.admin_operator = AdminOperatorProvides(
            charm=self.charm, relationship_name=self.relationship_name
        )

    def test_1(self):
        pass
