#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""feg-control-proxy.

TODO: Add comprehensive description.
Federation Gateway control proxy service.
"""


import logging

from ops.charm import CharmBase, InstallEvent, PebbleReadyEvent
from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import ExecError, Layer

logger = logging.getLogger(__name__)


class FegControlProxyCharm(CharmBase):
    """Main class that is instantiated everytime an event occurs."""

    BASE_CERTS_PATH = "/var/opt/magma/certs"
    BASE_NGHTTPX_CONFIG_PATH = "/var/opt/magma/tmp"

    def __init__(self, *args):
        """Initializes all events that need to be observed."""
        super().__init__(*args)
        self._container = self.unit.get_container(self.meta.name)
        self.framework.observe(
            self.on.magma_feg_control_proxy_pebble_ready,
            self._on_magma_feg_control_proxy_pebble_ready,
        )
        self.framework.observe(self.on.install, self._on_install)

    @staticmethod
    def _get_certificate_from_file(filename: str) -> str:
        with open(filename, "r") as file:
            certificate = file.read()
        return certificate

    @property
    def _controller_certs_are_stored(self) -> bool:
        """Returns whether controller certificate are stored.

        Returns:
            bool: Whether controller certificate are stored.
        """
        return self._container.exists(
            f"{self.BASE_CERTS_PATH}/controller.crt"
        ) and self._container.exists(  # noqa: W503
            f"{self.BASE_CERTS_PATH}/controller.key"
        )  # noqa: W503

    @property
    def _nghttpx_config_is_stored(self) -> bool:
        """Returns whether nghttpx config is stored.

        Returns:
            bool: Whether nghttpx config is stored.
        """
        return self._container.exists(f"{self.BASE_NGHTTPX_CONFIG_PATH}/nghttpx.conf")

    def _on_install(self, event: InstallEvent) -> None:
        """Juju event triggered only once when charm is installed.

        Args:
            event: Juju event
        Returns:
            None
        """
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return

        self._generate_nghttpx_config()
        self._push_certs()

    def _generate_nghttpx_config(self) -> None:
        """Generates nghttpx config file.

        Returns:
            None
        """
        logger.info("Generating nghttpx config file...")
        try:
            process_generate = self._container.exec(
                command=["/usr/local/bin/generate_nghttpx_config.py"]
            )
            process_generate.wait_output()
            # Deleting this line removes logs redirection to syslog, which is not installed
            # in the container. The service won't start without this change,
            # and logs will be hidden.
            # NOTE: This is also done in the official magma codebase. Look at
            # magma/lte/gateway/docker/docker-compose.yaml for more information.
            process_delete_line = self._container.exec(
                command=[
                    "sed",
                    "-i",
                    "/errorlog-syslog=/d",
                    f"{self.BASE_NGHTTPX_CONFIG_PATH}/nghttpx.conf",
                ]
            )
            process_delete_line.wait_output()
        except ExecError as e:
            logger.error("Exited with code %d. Stderr:", e.exit_code)
            for line in e.stderr.splitlines():
                logger.error("    %s", line)
            raise e
        logger.info("Successfully generated nghttpx config file")

    def _push_certs(self) -> None:
        """Pushes controller certs to container.

        Returns:
            None
        """
        logger.info("Pushing controller certs to container...")
        controller_crt = self._get_certificate_from_file(filename="src/test_controller.crt")
        controller_key = self._get_certificate_from_file(filename="src/test_controller.key")
        root_ca_key = self._get_certificate_from_file(filename="src/test_rootCA.key")
        root_ca_pem = self._get_certificate_from_file(filename="src/test_rootCA.pem")

        try:
            process_mkdir = self._container.exec(command=["mkdir", "-p", self.BASE_CERTS_PATH])
            process_mkdir.wait_output()

            self._container.push(
                path=f"{self.BASE_CERTS_PATH}/controller.crt", source=controller_crt
            )
            self._container.push(
                path=f"{self.BASE_CERTS_PATH}/controller.key", source=controller_key
            )
            self._container.push(path=f"{self.BASE_CERTS_PATH}/rootCA.key", source=root_ca_key)
            self._container.push(path=f"{self.BASE_CERTS_PATH}/rootCA.pem", source=root_ca_pem)
        except ExecError as e:
            logger.error("Exited with code %d. Stderr:", e.exit_code)
            for line in e.stderr.splitlines():
                logger.error("    %s", line)
            raise e
        logger.info("Successfully pushed controller certs to container")

    def _on_magma_feg_control_proxy_pebble_ready(self, event: PebbleReadyEvent) -> None:
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
        if not self._nghttpx_config_is_stored:
            self.unit.status = WaitingStatus("Waiting for nghttpx config to be available")
            event.defer()
            return
        if not self._controller_certs_are_stored:
            self.unit.status = WaitingStatus("Waiting for controller certs to be available")
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
                        "command": f"nghttpx --conf {self.BASE_NGHTTPX_CONFIG_PATH}/nghttpx.conf "
                        f"{self.BASE_CERTS_PATH}/controller.key "
                        f"{self.BASE_CERTS_PATH}/controller.crt",
                        "startup": "enabled",
                    }
                },
            }
        )


if __name__ == "__main__":
    main(FegControlProxyCharm)
