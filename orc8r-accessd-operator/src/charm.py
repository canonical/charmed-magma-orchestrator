#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Stores, manages and verifies operator identity objects."""

from charms.magma_orc8r_libs.v1.orc8r_base_db import Orc8rBase
from charms.observability_libs.v1.kubernetes_service_patch import (
    KubernetesServicePatch,
    ServicePort,
)
from ops.charm import CharmBase
from ops.main import main


class MagmaOrc8rAccessdCharm(CharmBase):
    """Creates a new instance of this object for each event."""

    def __init__(self, *args):
        """Uses the Orc8rBase library to manage its events."""
        super().__init__(*args)
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[
                ServicePort(name="grpc", port=9180, targetPort=9091),
                ServicePort(name="grpc-internal", port=9091, targetPort=9191),
            ],
            additional_labels={"app.kubernetes.io/part-of": "orc8r-app"},
        )
        startup_command = "accessd -logtostderr=true -v=0"
        self._orc8r_base = Orc8rBase(self, startup_command=startup_command)


if __name__ == "__main__":
    main(MagmaOrc8rAccessdCharm)
