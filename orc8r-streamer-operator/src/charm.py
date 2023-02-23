#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Fetches updates for various data streams and returning these to the gateways."""

from charms.magma_orc8r_libs.v0.orc8r_base import Orc8rBase
from charms.observability_libs.v1.kubernetes_service_patch import (
    KubernetesServicePatch,
    ServicePort,
)
from ops.charm import CharmBase
from ops.main import main


class MagmaOrc8rStreamer(CharmBase):
    """An instance of this object everytime an event occurs."""

    def __init__(self, *args):
        """Uses the Orc8rBase library to manage events."""
        super().__init__(*args)
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[ServicePort(name="grpc", port=9180, targetPort=9082)],
            additional_labels={"app.kubernetes.io/part-of": "orc8r-app"},
        )
        startup_command = "/usr/bin/envdir /var/opt/magma/envdir /var/opt/magma/bin/streamer -logtostderr=true -v=0"
        self._orc8r_base = Orc8rBase(self, startup_command=startup_command)


if __name__ == "__main__":
    main(MagmaOrc8rStreamer)
