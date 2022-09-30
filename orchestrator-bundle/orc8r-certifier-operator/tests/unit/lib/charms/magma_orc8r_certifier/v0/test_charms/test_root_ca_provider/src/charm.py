#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

from charms.magma_orc8r_certifier.v0.cert_root_ca import CertRootCAProvides
from ops.charm import CharmBase
from ops.main import main

logger = logging.getLogger(__name__)


class WhateverCharm(CharmBase):
    TEST_CERTIFICATE = ""

    def __init__(self, *args):
        """Creates a new instance of this object for each event."""
        super().__init__(*args)
        self.root_ca_cert_provider = CertRootCAProvides(self, "cert-root-ca")

        self.framework.observe(
            self.root_ca_cert_provider.on.certificate_request, self._on_certificate_request
        )

    def _on_certificate_request(self, event):
        self.root_ca_cert_provider.set_certificate(
            relation_id=event.relation_id,
            certificate=self.TEST_CERTIFICATE,
        )


if __name__ == "__main__":
    main(WhateverCharm)
