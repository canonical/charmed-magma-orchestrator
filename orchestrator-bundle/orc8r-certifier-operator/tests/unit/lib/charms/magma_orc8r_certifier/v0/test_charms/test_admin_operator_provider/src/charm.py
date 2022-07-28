#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

from charms.magma_orc8r_certifier.v0.cert_admin_operator import (
    CertAdminOperatorProvides,
)
from ops.charm import CharmBase
from ops.main import main

logger = logging.getLogger(__name__)


class WhateverCharm(CharmBase):
    def __init__(self, *args):
        """Creates a new instance of this object for each event."""
        super().__init__(*args)
        self.admin_operator = CertAdminOperatorProvides(self, "cert-admin-operator")


if __name__ == "__main__":
    main(WhateverCharm)
