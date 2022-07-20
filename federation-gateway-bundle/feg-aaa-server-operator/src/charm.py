#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import logging

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer

logger = logging.getLogger(__name__)


class FegAaaServerCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.container_name = self.service_name = self.meta.name
        self.container = self.unit.get_container(self.container_name)
        self.framework.observe(
            self.on.magma_feg_aaa_server_pebble_ready, self._on_magma_feg_aaa_server_pebble_ready
        )

    def _on_magma_feg_aaa_server_pebble_ready(self, event) -> None:
        if self.container.can_connect():
            self.unit.status = MaintenanceStatus("Configuring pod")
            pebble_layer = self._pebble_layer
            plan = self.container.get_plan()
            if plan.services != pebble_layer.services:
                self.container.add_layer(self.container_name, pebble_layer, combine=True)
                self.container.replan()
                logger.info(f"Restarted container {self.service_name}")
                self.unit.status = ActiveStatus()
        else:
            self.unit.status = WaitingStatus("Waiting for container to be ready...")
            event.defer()

    @property
    def _pebble_layer(self) -> Layer:
        return Layer(
            {
                "summary": f"{self.service_name} layer",
                "description": f"pebble config layer for {self.service_name}",
                "services": {
                    self.service_name: {
                        "override": "replace",
                        "summary": self.service_name,
                        "command": "envdir "
                        "/var/opt/magma/envdir "
                        "/var/opt/magma/bin/aaa_server "
                        "-logtostderr=true "
                        "-v=0",
                        "startup": "enabled",
                    }
                },
            }
        )


if __name__ == "__main__":
    main(FegAaaServerCharm)
