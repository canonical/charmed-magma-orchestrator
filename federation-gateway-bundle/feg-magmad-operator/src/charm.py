#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.


import logging

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer

logger = logging.getLogger(__name__)


class FegMagmadCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.container_name = self.service_name = self.meta.name
        self.container = self.unit.get_container(self.container_name)
        self.framework.observe(
            self.on.magma_feg_magmad_pebble_ready, self._on_magma_feg_magmad_pebble_ready
        )

    def _on_magma_feg_magmad_pebble_ready(self, event) -> None:
        if not self.container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready...")
            event.defer()

        self.unit.status = MaintenanceStatus("Configuring pod")
        pebble_layer = self._pebble_layer
        plan = self.container.get_plan()
        if plan.services != pebble_layer.services:
            self.container.add_layer(self.container_name, pebble_layer, combine=True)
            self.container.replan()
            logger.info(f"Restarted container {self.service_name}")
            self.unit.status = ActiveStatus()

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
                        "command": "python3.8 -m magma.magmad.main",
                        "startup": "enabled",
                    }
                },
            }
        )


if __name__ == "__main__":
    main(FegMagmadCharm)
