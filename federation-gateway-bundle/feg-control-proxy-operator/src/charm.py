#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""feg-control-proxy.

TODO: Add comprehensive description.
Federation Gateway control proxy service.
"""


import logging
from typing import Union

from ops.charm import CharmBase, ConfigChangedEvent, InstallEvent, PebbleReadyEvent
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import ExecError, Layer

logger = logging.getLogger(__name__)


class FegControlProxyCharm(CharmBase):
    """Main class that is instantiated everytime an event occurs."""

    BASE_CERTIFICATES_PATH = "/var/opt/magma/certs"
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
        self.framework.observe(self.on.config_changed, self._on_config_changed)

    @staticmethod
    def _get_certificate_from_file(filename: str) -> str:
        with open(filename, "r") as file:
            certificate = file.read()
        return certificate

    @property
    def _controller_certificates_are_stored(self) -> bool:
        """Returns whether controller certificate are stored.

        Returns:
            bool: Whether controller certificate are stored.
        """
        return self._container.exists(
            f"{self.BASE_CERTIFICATES_PATH}/controller.crt"
        ) and self._container.exists(  # noqa: W503
            f"{self.BASE_CERTIFICATES_PATH}/controller.key"
        )  # noqa: W503

    @property
    def _nghttpx_config_is_stored(self) -> bool:
        """Returns whether nghttpx config is stored.

        Returns:
            bool: Whether nghttpx config is stored.
        """
        return self._container.exists(f"{self.BASE_NGHTTPX_CONFIG_PATH}/nghttpx.conf")

    # TODO: Probably we could remove this check whenever
    # we integrate with orc8r for providing certificates.
    @property
    def _certificates_are_valid(self) -> bool:
        """Returns whether config certificates are valid.

        Args:
            None
        Returns:
            bool: Whether config certificates are valid.
        """
        (
            controller_crt,
            controller_key,
            root_ca_pem,
            root_ca_key,
        ) = self._get_certs_from_config().values()
        if not self._certificate_is_valid(controller_crt):
            return False
        if not self._key_is_valid(controller_key):
            return False
        if not self._certificate_is_valid(root_ca_pem):
            return False
        if not self._key_is_valid(root_ca_key):
            return False
        return True

    # TODO: Probably we could remove this check whenever
    # we integrate with orc8r for providing certificates.
    @staticmethod
    def _certificate_is_valid(certificate: str) -> bool:
        """Returns whether given certificate is valid.

        Returns:
            bool: Whether certificate is valid.
        """
        if certificate is None:
            return False
        if certificate == "":
            return False
        return True

    @staticmethod
    def _key_is_valid(key: str) -> bool:
        """Returns whether given key is valid.

        Args:
            key: Key to validate.

        Returns:
            bool: Whether key is valid.
        """
        if key is None:
            return False
        if key == "":
            return False
        return True

    def _generate_nghttpx_config(self) -> None:
        """Generates nghttpx config file.

        Generates nghttpx and deletes line that prevents logs redirection to syslog.
        This prevents the service from crashing, as there is no syslog in the container.
        NOTE: This is also done in the official magma codebase. Look at
        https://github.com/magma/magma/blob/master/lte/gateway/docker/docker-compose.yaml
        for more information.

        Returns:
            None
        """
        logger.info("Generating nghttpx config file...")
        try:
            process_generate = self._container.exec(
                command=["/usr/local/bin/generate_nghttpx_config.py"]
            )
            process_generate.wait_output()
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

    def _get_certs_from_config(self) -> dict:
        """Returns certificates from config.

        Returns:
            dict: Dictionary with certificates.
        """
        return {
            "controller_crt": self.model.config.get("controller-crt"),
            "controller_key": self.model.config.get("controller-key"),
            "root_ca_pem": self.model.config.get("root-ca-pem"),
            "root_ca_key": self.model.config.get("root-ca-key"),
        }

    def _push_certificates(self) -> None:
        """Pushes controller certs to container.

        Returns:
            None
        """
        logger.info("Pushing controller certs to container...")
        (
            controller_crt,
            controller_key,
            root_ca_pem,
            root_ca_key,
        ) = self._get_certs_from_config().values()

        try:
            process_mkdir = self._container.exec(
                command=["mkdir", "-p", self.BASE_CERTIFICATES_PATH]
            )
            process_mkdir.wait_output()

            self._container.push(
                path=f"{self.BASE_CERTIFICATES_PATH}/controller.crt", source=controller_crt
            )
            self._container.push(
                path=f"{self.BASE_CERTIFICATES_PATH}/controller.key", source=controller_key
            )
            self._container.push(
                path=f"{self.BASE_CERTIFICATES_PATH}/rootCA.pem", source=root_ca_pem
            )
            self._container.push(
                path=f"{self.BASE_CERTIFICATES_PATH}/rootCA.key", source=root_ca_key
            )
        except ExecError as e:
            logger.error("Exited with code %d. Stderr:", e.exit_code)
            for line in e.stderr.splitlines():
                logger.error("    %s", line)
            raise e
        logger.info("Successfully pushed controller certs to container")

    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        """Juju event triggered when config is changed.

        It will fetch the certificates from the config file and push them to the container.

        Args:
            event (ConfigChangedEvent): Juju event
        Returns:
            None
        """
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready...")
            event.defer()
            return
        if not self._certificates_are_valid:
            event.defer()
            return

        self._push_certificates()
        self._on_magma_feg_control_proxy_pebble_ready(event)

    def _on_install(self, event: InstallEvent) -> None:
        """Juju event triggered only once when charm is installed.

        Args:
            event (InstallEvent): Juju event
        Returns:
            None
        """
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return

        self._generate_nghttpx_config()

    def _on_magma_feg_control_proxy_pebble_ready(
        self, event: Union[PebbleReadyEvent, ConfigChangedEvent]
    ) -> None:
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
        if not (self._controller_certificates_are_stored and self._certificates_are_valid):
            self.unit.status = BlockedStatus(
                "Provide valid certificates with `juju config feg-control-proxy --file <config_file.yaml>`"
            )
            event.defer()
            return
        self._configure_pebble(event)

    def _configure_pebble(self, event: Union[PebbleReadyEvent, ConfigChangedEvent]) -> None:
        """Configures Pebble layer.

        Creates nginx service and starts it.

        Args:
            event: Juju event.

        Returns:
            None
        """
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready...")
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
                        f"{self.BASE_CERTIFICATES_PATH}/controller.key "
                        f"{self.BASE_CERTIFICATES_PATH}/controller.crt",
                        "startup": "enabled",
                    }
                },
            }
        )


if __name__ == "__main__":
    main(FegControlProxyCharm)
