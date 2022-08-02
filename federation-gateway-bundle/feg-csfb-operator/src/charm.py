#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.


import logging

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer

logger = logging.getLogger(__name__)


class FegCsfbCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.container = self.unit.get_container(self.meta.name)
        self.framework.observe(
            self.on.magma_feg_csfb_pebble_ready, self._on_magma_feg_csfb_pebble_ready
        )

    def _on_magma_feg_csfb_pebble_ready(self, event) -> None:
        if not self.container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready...")
            event.defer()

        pebble_layer = self._pebble_layer
        plan = self.container.get_plan()
        if plan.services != pebble_layer.services:
            self.unit.status = MaintenanceStatus("Configuring pod")
            self.container.add_layer(self.meta.name, pebble_layer, combine=True)
            self.container.replan()
            logger.info(f"Restarted container {self.meta.name}")
            self.unit.status = ActiveStatus()

    @property
    def _pebble_layer(self) -> Layer:
        return Layer(
            {
                "summary": f"{self.meta.name} layer",
                "description": f"pebble config layer for {self.meta.name}",
                "services": {
                    self.meta.name: {
                        "override": "replace",
                        "summary": self.meta.name,
                        "command": "envdir "
                        "/var/opt/magma/envdir "
                        "/var/opt/magma/bin/csfb "
                        "-logtostderr=true "
                        "-v=0",
                        "startup": "enabled",
                    }
                },
            }
        )


if __name__ == "__main__":
    main(FegCsfbCharm)
