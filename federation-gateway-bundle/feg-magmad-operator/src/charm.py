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
        self.container = self.unit.get_container(self.meta.name)
        self.framework.observe(
            self.on.magma_feg_magmad_pebble_ready, self._on_magma_feg_magmad_pebble_ready
        )

    def _on_magma_feg_magmad_pebble_ready(self, event) -> None:
        if not self.container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready...")
            event.defer()

        pebble_layer = self._pebble_layer
        plan = self.container.get_plan()
        if plan.services != pebble_layer.services:
            self.unit.status = MaintenanceStatus("Configuring pod")
            self.container.add_layer(self.meta.name, pebble_layer, combine=True)
            self.container.replan()
            self.unit.status = ActiveStatus()

    @property
    def _pebble_layer(self) -> Layer:
        return Layer(
            {
                "services": {
                        "override": "replace",
                        "command": "python3.8 -m magma.magmad.main",
                        "startup": "enabled",
                    }
                },
            }
        )


if __name__ == "__main__":
    main(FegMagmadCharm)
