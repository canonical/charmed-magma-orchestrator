#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

from charms.magma_orc8r_libs.v0.orc8r_base import Orc8rBase
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from ops.charm import CharmBase
from ops.main import main


class MagmaOrc8rHACharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        """
        An instance of this object everytime an event occurs
        """
        super().__init__(*args)
        self._service_patcher = KubernetesServicePatch(self, [("grpc", 9180, 9119)])
        startup_command = (
            "/usr/bin/envdir "
            "/var/opt/magma/envdir "
            "/var/opt/magma/bin/ha "
            "-logtostderr=true "
            "-v=0"
        )
        self._orc8r_base = Orc8rBase(
            self,
            service_name="magma-orc8r-ha",
            startup_command=startup_command,
            pebble_ready_event=self.on.magma_orc8r_ha_pebble_ready,
        )


if __name__ == "__main__":
    main(MagmaOrc8rHACharm)
