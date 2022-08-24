#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""feg-redis.

TODO: Add comprehensive description.
Federation Gateway redis service.
"""


import logging

from ops.charm import CharmBase, InstallEvent, PebbleReadyEvent
from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import ExecError, Layer

logger = logging.getLogger(__name__)


class FegRedisCharm(CharmBase):
    """Main class that is instantiated everytime an event occurs."""

    BASE_SERVICE_CONFIG_PATH = "/var/opt/magma/tmp"

    def __init__(self, *args):
        """Initializes all events that need to be observed."""
        super().__init__(*args)
        self._container = self.unit.get_container(self.meta.name)
        self.framework.observe(
            self.on.magma_feg_redis_pebble_ready, self._on_magma_feg_redis_pebble_ready
        )
        self.framework.observe(self.on.install, self._on_install)

    @property
    def _service_config_is_stored(self) -> bool:
        """Checks if service config file is stored.

        Returns:
            bool: Whether service config file is stored.
        """
        return self._container.exists(f"{self.BASE_SERVICE_CONFIG_PATH}/redis.conf")

    def _generate_service_config(self) -> None:
        """Generates service config file.

        Returns:
            None
        """
        logger.info("Generating service config file...")
        try:
            process_generate = self._container.exec(
                command=[
                    "/usr/local/bin/generate_service_config.py",
                    "--service=redis",
                    "--template=redis",
                ]
            )
            process_generate.wait_output()
        except ExecError as e:
            logger.error("Exited with code %d. Stderr:", e.exit_code)
            for line in e.stderr.splitlines():  # type: ignore[union-attr]
                logger.error("    %s", line)
            raise e
        logger.info("Successfully generated service config file")

    def _on_install(self, event: InstallEvent) -> None:
        """Juju event triggered when install hook is called.

        Args:
            event (InstallEvent): Juju event
        Returns:
            None
        """
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return

        self._generate_service_config()

    def _on_magma_feg_redis_pebble_ready(self, event: PebbleReadyEvent) -> None:
        """Juju event triggered when pebble is ready.

        Args:
            event (PebbleReadyEvent): Juju event
        Returns:
            None
        """
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready...")
            event.defer()
            return
        if not self._service_config_is_stored:
            self.unit.status = WaitingStatus("Waiting for service config to be available")
            event.defer()
            return

        pebble_layer = self._pebble_layer
        plan = self._container.get_plan()
        if plan.services != pebble_layer.services:
            self.unit.status = MaintenanceStatus("Configuring pod")
            self._container.add_layer(self.meta.name, pebble_layer, combine=True)
            self._container.replan()
            logger.info(f"Restarted container {self.meta.name}")
            self.unit.status = ActiveStatus()

    @property
    def _pebble_layer(self) -> Layer:
        """Returns Pebble layer object containing the workload startup service.

        Returns:
            Layer: Pebble layer
        """
        return Layer(
            {
                "summary": f"{self.meta.name} layer",
                "description": f"pebble config layer for {self.meta.name}",
                "services": {
                    self.meta.name: {
                        "override": "replace",
                        "summary": self.meta.name,
                        "command": '/bin/bash -c "/usr/bin/redis-server /var/opt/magma/tmp/redis.conf --daemonize no && /usr/bin/redis-cli shutdown"',
                        "startup": "enabled",
                    }
                },
            }
        )


if __name__ == "__main__":
    main(FegRedisCharm)
