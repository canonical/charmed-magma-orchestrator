#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

from charms.fluentd_certificate.v0.fluentd_certificate import FluentdCertificateRequires
from ops.charm import CharmBase
from ops.main import main

logger = logging.getLogger(__name__)


class DummyRequirerCharm(CharmBase):

    CERT_PATH = "dummy cert path"
    CERTIFICATE_SIGNING_REQUEST = "dummy csr"

    def __init__(self, *args):
        """Creates a new instance of this object for each event."""
        super().__init__(*args)
        self.fluentd_certificate_requirer = FluentdCertificateRequires(self, "cert-fluentd")
        
        self.framework.observe(
            self.on.cert_fluentd_relation_joined, self._on_cert_fluentd_relation_joined
        )
        self.framework.observe(
            self.fluentd_certificate_requirer.on.fluentd_certificate_available, self._on_certificate_available
        )
        
    def _on_cert_fluentd_relation_joined(self, event):
        self.fluentd_certificate_requirer.set_certificate_signing_request(
            certificate_signing_request=self.CERTIFICATE_SIGNING_REQUEST
        )

    def _on_certificate_available(self, event):
        self.model.unit.get_container("dummy-container").push(self.CERT_PATH, event.certificate)


if __name__ == "__main__":
    main(DummyRequirerCharm)