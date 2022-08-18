#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""feg-health.

Provides health updates to the orc8r to be used for achieving highly available
federated gateway clusters.
"""


import logging

from ops.charm import CharmBase, PebbleReadyEvent
from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer

logger = logging.getLogger(__name__)


class FegHealthCharm(CharmBase):
    """Main class that is instantiated everytime an event occurs."""

    def __init__(self, *args):
        """Initializes all events that need to be observed."""
        super().__init__(*args)
        self.container_name = self.service_name = self.meta.name
        self.container = self.unit.get_container(self.container_name)
        self.framework.observe(
            self.on.magma_feg_health_pebble_ready, self._on_magma_feg_health_pebble_ready
        )

    def _on_magma_feg_health_pebble_ready(self, event: PebbleReadyEvent) -> None:
        """Juju event triggered when pebble is ready.

        Args:
            event (PebbleReadyEvent): Juju event
        Returns:
            None
        """
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
        """Returns Pebble layer object containing the workload startup service.

        Returns:
            Layer: Pebble layer
        """
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
                        "/var/opt/magma/bin/gateway_health "
                        "-logtostderr=true "
                        "-v=0",
                        "startup": "enabled",
                    }
                },
            }
        )


if __name__ == "__main__":
    main(FegHealthCharm)