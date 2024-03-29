#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Verifies API request access control and reverse proxies requests."""

from charms.magma_orc8r_libs.v0.orc8r_base import Orc8rBase
from charms.observability_libs.v1.kubernetes_service_patch import (
    KubernetesServicePatch,
    ServicePort,
)
from ops.charm import CharmBase
from ops.main import main


class MagmaOrc8rObsidianCharm(CharmBase):
    """An instance of this object everytime an event occurs."""

    def __init__(self, *args):
        """Uses the Orc8rBase library to manage events."""
        super().__init__(*args)
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[
                ServicePort(name="grpc", port=9180, targetPort=9093),
                ServicePort(name="http", port=8080, targetPort=9081),
                ServicePort(name="grpc-internal", port=9190, targetPort=9193),
            ],
            additional_labels={"app.kubernetes.io/part-of": "orc8r-app"},
        )
        startup_command = "obsidian -logtostderr=true -v=0"
        self._orc8r_base = Orc8rBase(self, startup_command=startup_command)


if __name__ == "__main__":
    main(MagmaOrc8rObsidianCharm)
