#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

from charms.magma_orc8r_certifier.v0.cert_root import CertRootCARequires
from ops.charm import CharmBase
from ops.main import main

logger = logging.getLogger(__name__)


class WhateverCharm(CharmBase):
    CERT_PATH = ""

    def __init__(self, *args):
        """Creates a new instance of this object for each event."""
        super().__init__(*args)
        self.root_cert = CertRootCARequires(self, "cert-root")

        self.framework.observe(
            self.root_cert.on.certificate_available, self._on_certificate_available
        )

    def _on_certificate_available(self, event):
        self.model.unit.get_container("whatever-container").push(self.CERT_PATH, event.certificate)


if __name__ == "__main__":
    main(WhateverCharm)
