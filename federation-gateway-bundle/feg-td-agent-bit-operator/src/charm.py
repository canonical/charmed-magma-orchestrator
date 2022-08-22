#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""feg-td-agent-bit.

TODO: Add comprehensive description.
Federation Gateway td-agent-bit service.
"""


import logging

from ops.charm import CharmBase, InstallEvent, PebbleReadyEvent
from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import ExecError, Layer

logger = logging.getLogger(__name__)


class FegTdAgentBitCharm(CharmBase):
    """Main class that is instantiated everytime an event occurs."""

    BASE_FLUENT_BIT_CONFIG_PATH = "/var/opt/magma/tmp"

    def __init__(self, *args):
        """Initializes all events that need to be observed."""
        super().__init__(*args)
        self._container = self.unit.get_container(self.meta.name)
        self.framework.observe(
            self.on.magma_feg_td_agent_bit_pebble_ready,
            self._on_magma_feg_td_agent_bit_pebble_ready,
        )
        self.framework.observe(self.on.install, self._on_install)

    @property
    def _fluent_bit_config_is_stored(self) -> bool:
        """Returns whether fluent bit config is stored.

        Returns:
            bool: Whether fluent bit config is stored.
        """
        return self._container.exists(f"{self.BASE_FLUENT_BIT_CONFIG_PATH}/td-agent-bit.conf")

    def _generate_fluent_bit_config(self) -> None:
        """Generates fluent bit config file.

        Returns:
            None
        """
        logger.info("Generating fluent bit config file...")
        try:
            process_generate = self._container.exec(
                command=["/usr/local/bin/generate_fluent_bit_config.py"]
            )
            process_generate.wait_output()
        except ExecError as e:
            logger.error("Exited with code %d. Stderr:", e.exit_code)
            for line in e.stderr.splitlines():
                logger.error("    %s", line)
            raise e
        logger.info("Successfully generated fluent bit config file")

    def _on_install(self, event: InstallEvent) -> None:
        """Juju event triggered when charm is installed.

        Args:
            event (InstallEvent): Juju event
        Returns:
            None
        """
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready...")
            event.defer()
            return

        self._generate_fluent_bit_config()

    def _on_magma_feg_td_agent_bit_pebble_ready(self, event: PebbleReadyEvent) -> None:
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
        if not self._fluent_bit_config_is_stored:
            self.unit.status = WaitingStatus("Waiting for fluent bit config to be available")
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
                        "command": "/opt/td-agent-bit/bin/td-agent-bit -c "
                        "'/var/opt/magma/tmp/td-agent-bit.conf'",
                        "startup": "enabled",
                    }
                },
            }
        )


if __name__ == "__main__":
    main(FegTdAgentBitCharm)
