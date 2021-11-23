#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus
from ops.pebble import Layer

logger = logging.getLogger(__name__)


class MagmaOrc8rEventdCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self._container_name = self._service_name = "magma-orc8r-eventd"
        self._container = self.unit.get_container(self._container_name)
        self.framework.observe(
            self.on.magma_orc8r_eventd_pebble_ready,
            self._on_magma_orc8r_eventd_pebble_ready,
        )
        self._service_patcher = KubernetesServicePatch(
            self, [("grpc", 9180, 9121), ("http", 8080, 10121)]
        )

    def _on_magma_orc8r_eventd_pebble_ready(self, event):
        """Triggered when pebble is ready."""
        self.unit.status = MaintenanceStatus("Configuring pebble layer")
        self._create_pebble_layer()
        self.unit.status = ActiveStatus()

    def _create_pebble_layer(self):
        """Adds layer to pebble config if the proposed config is different from the current one."""
        pebble_layer = self._pebble_layer
        plan = self._container.get_plan()
        if plan.services != pebble_layer.services:
            self._container.add_layer(self._container_name, pebble_layer, combine=True)
            self._container.restart(self._service_name)
            logger.info(f"Restarted container {self._service_name}")

    @property
    def _pebble_layer(self) -> Layer:
        """Returns pebble layer for the charm."""
        return Layer(
            {
                "summary": f"{self._container_name} pebble layer",
                "services": {
                    self._service_name: {
                        "override": "replace",
                        "startup": "enabled",
                        "command": "/usr/bin/envdir "
                        "/var/opt/magma/envdir "
                        "/var/opt/magma/bin/eventd "
                        "-run_echo_server=true "
                        "-logtostderr=true "
                        "-v=0",
                    },
                },
            },
        )


if __name__ == "__main__":
    main(MagmaOrc8rEventdCharm)
