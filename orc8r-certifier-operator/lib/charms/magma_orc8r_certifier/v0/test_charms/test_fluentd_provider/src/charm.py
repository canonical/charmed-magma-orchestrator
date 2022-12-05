# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

from charms.fluentd_certificate.v0.fluentd_certificate import FluentdCertProvides
from ops.charm import CharmBase
from ops.main import main

logger = logging.getLogger(__name__)


class DummyProviderCharm(CharmBase):
    TEST_CERTIFICATE = ""

    def __init__(self, *args):
        """Creates a new instance of this object for each event."""
        super().__init__(*args)
        self.fluentd_certificate_provider = FluentdCertProvides(self, "cert-fluentd")

        self.framework.observe(
            self.fluentd_certificate_provider.on.certificate_request, self._on_fluentd_certificate_signing_request
        )

    def _on_fluentd_certificate_signing_request(self, event):
        self.fluentd_certificate_provider.set_fluentd_certificate(
            relation_id=event.relation_id,
            certificate=self.TEST_CERTIFICATE,
        )


if __name__ == "__main__":
    main(DummyProviderCharm)