# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

from charms.magma_orc8r_certifier.v0.cert_fluentd import CertFluentdProvides
from ops.charm import CharmBase
from ops.main import main

logger = logging.getLogger(__name__)


class WhateverCharm(CharmBase):
    TEST_CERTIFICATE = ""
    PRIVATE_KEY = ""

    def __init__(self, *args):
        """Creates a new instance of this object for each event."""
        super().__init__(*args)
        self.fluentd_cert_provider = CertFluentdProvides(self, "cert-fluentd")

        self.framework.observe(
            self.fluentd_cert_provider.on.certificate_request, self._on_certificate_request
        )

    def _on_certificate_request(self, event):
        self.fluentd_cert_provider.set_certificate(
            relation_id=event.relation_id,
            certificate=self.TEST_CERTIFICATE,
            private_key=self.PRIVATE_KEY,
        )


if __name__ == "__main__":
    main(WhateverCharm)
