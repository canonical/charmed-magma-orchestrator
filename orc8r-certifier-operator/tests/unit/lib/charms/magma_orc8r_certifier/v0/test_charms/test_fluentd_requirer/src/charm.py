#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

from charms.magma_orc8r_certifier.v0.cert_fluentd import CertFluentdRequires
from ops.charm import CharmBase
from ops.main import main

logger = logging.getLogger(__name__)


class WhateverCharm(CharmBase):
    CERT_PATH = ""
    PRIVATE_KEY_PATH = ""

    def __init__(self, *args):
        """Creates a new instance of this object for each event."""
        super().__init__(*args)
        self.fluentd_cert_requirer = CertFluentdRequires(self, "cert-fluentd")

        self.framework.observe(
            self.fluentd_cert_requirer.on.certificate_available, self._on_certificate_available
        )

    def _on_certificate_available(self, event):
        self.model.unit.get_container("whatever-container").push(self.CERT_PATH, event.certificate)
        self.model.unit.get_container("whatever-container").push(
            self.PRIVATE_KEY_PATH, event.private_key
        )


if __name__ == "__main__":
    main(WhateverCharm)
