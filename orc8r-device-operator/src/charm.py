#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Maintains configurations and metadata for devices in the network."""

from charms.magma_orc8r_libs.v0.orc8r_base_db import Orc8rBase
from charms.observability_libs.v1.kubernetes_service_patch import (
    KubernetesServicePatch,
    ServicePort,
)
from ops.charm import CharmBase
from ops.main import main


class MagmaOrc8rDeviceCharm(CharmBase):
    """Creates a new instance of this object for each event."""

    STARTUP_COMMAND = "device -logtostderr=true -v=0"

    def __init__(self, *args):
        """Uses the Orc8rBase library to manage events."""
        super().__init__(*args)
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[
                ServicePort(name="grpc", port=9180, targetPort=9106),
                ServicePort(name="grpc-internal", port=9190, targetPort=9306),
            ],
            additional_labels={"app.kubernetes.io/part-of": "orc8r-app"},
        )
        self._orc8r_base = Orc8rBase(self, startup_command=self.STARTUP_COMMAND)


if __name__ == "__main__":
    main(MagmaOrc8rDeviceCharm)
