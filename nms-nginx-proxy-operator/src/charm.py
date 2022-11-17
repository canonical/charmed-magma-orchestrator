#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""magma-nms-nginx-proxy.

This charm is an nginx web server that proxies communication between NMS UI and MagmaLTE.
"""

import logging
from typing import Union

from charms.magma_orc8r_certifier.v0.cert_controller import (
    CertControllerRequires,
    CertificateAvailableEvent,
)
from charms.observability_libs.v1.kubernetes_service_patch import (
    KubernetesServicePatch,
    ServicePort,
)
from ops.charm import CharmBase, InstallEvent, PebbleReadyEvent
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer

logger = logging.getLogger(__name__)


class MagmaNmsNginxProxyCharm(CharmBase):
    """Main class that is instantiated everytime an event occurs."""

    BASE_NGINX_PATH = "/etc/nginx/conf.d"
    NGINX_CONFIG_FILE_NAME = "nginx_proxy_ssl.conf"

    def __init__(self, *args):
        """Initializes all events that need to be observed."""
        super().__init__(*args)
        self._container_name = self._service_name = "magma-nms-nginx-proxy"
        self._container = self.unit.get_container(self._container_name)
        self.cert_controller = CertControllerRequires(self, "cert-controller")
        self.service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[ServicePort(name="https", port=443)],
            service_type="LoadBalancer",
            service_name="nginx-proxy",
            additional_labels={"app.kubernetes.io/part-of": "magma"},
        )
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(
            self.on.magma_nms_nginx_proxy_pebble_ready, self._on_magma_nms_nginx_proxy_pebble_ready
        )
        self.framework.observe(
            self.cert_controller.on.certificate_available, self._on_certificate_available
        )

    @property
    def _nginx_config_file_is_stored(self) -> bool:
        """Returns whether nginx config file is stored in workload container.

        Returns:
            bool: True/False
        """
        return self._container.exists(f"{self.BASE_NGINX_PATH}/{self.NGINX_CONFIG_FILE_NAME}")

    @property
    def _cert_controller_relation_created(self) -> bool:
        """Returns whether `cert-controller` relation is created.

        Returns:
            bool :True/False
        """
        return self._relation_created("cert-controller")

    @property
    def _magmalte_relation_created(self) -> bool:
        """Returns whether `magmalte` relation is created.

        Returns:
            bool: True/False
        """
        return self._relation_created("magma-nms-magmalte")

    @property
    def _certs_are_stored(self) -> bool:
        return self._container.exists(
            f"{self.BASE_NGINX_PATH}/nms_nginx.pem"
        ) and self._container.exists(f"{self.BASE_NGINX_PATH}/nms_nginx.key.pem")

    @property
    def _pebble_layer(self) -> Layer:
        """Returns pebble layer with workload service.

        Returns:
            Layer: Pebble Layer
        """
        return Layer(
            {
                "summary": f"{self._service_name} pebble layer",
                "services": {
                    self._service_name: {
                        "override": "replace",
                        "startup": "enabled",
                        "command": "nginx",
                    }
                },
            }
        )

    def _relation_created(self, relation_name: str) -> bool:
        """Returns whether given relation was created.

        Args:
            relation_name (str): Relation name

        Returns:
            bool: True/False
        """
        try:
            relation = self.model.get_relation(relation_name)
            return bool(relation)
        except KeyError:
            return False

    def _on_install(self, event: InstallEvent) -> None:
        """Triggered once when the charm is installed.

        Args:
            event: Juju event.

        Returns:
            None
        """
        if not self._container.can_connect():
            event.defer()
            return
        self._write_nginx_config_file()

    def _write_nginx_config_file(self) -> None:
        """Writes nginx config file to workload container.

        Returns:
            None
        """
        # TODO: Replace the proxy_pass line content with data coming from the magmalte relation
        config_file = (
            "server {\n"
            "listen 443;\n"
            "ssl on;\n"
            f"ssl_certificate {self.BASE_NGINX_PATH}/nms_nginx.pem;\n"
            f"ssl_certificate_key {self.BASE_NGINX_PATH}/nms_nginx.key.pem;\n"
            "location / {\n"
            "proxy_pass http://magmalte:8081;\n"
            "proxy_set_header Host $http_host;\n"
            "proxy_set_header X-Forwarded-Proto $scheme;\n"
            "}\n"
            "}"
        )
        self._container.push(
            path=f"{self.BASE_NGINX_PATH}/{self.NGINX_CONFIG_FILE_NAME}", source=config_file
        )

    def _on_magma_nms_nginx_proxy_pebble_ready(
        self, event: Union[PebbleReadyEvent, CertificateAvailableEvent]
    ) -> None:
        """Configures magma-nms-nginx-proxy pebble layer.

        Args:
            event: Juju event

        Returns:
            None
        """
        if not self._magmalte_relation_created:
            self.unit.status = BlockedStatus("Waiting for magmalte relation to be created")
            event.defer()
            return
        if not self._cert_controller_relation_created:
            self.unit.status = BlockedStatus("Waiting for cert-controller relation to be created")
            event.defer()
            return
        if not self._certs_are_stored:
            self.unit.status = WaitingStatus("Waiting for certs to be available")
            event.defer()
            return
        if not self._nginx_config_file_is_stored:
            self.unit.status = WaitingStatus("Waiting for NGINX Config file to be stored")
            event.defer()
            return
        self._configure_pebble(event)

    def _configure_pebble(self, event: Union[PebbleReadyEvent, CertificateAvailableEvent]) -> None:
        """Configures Pebble layer.

        Creates nginx service and starts it.

        Args:
            event: Juju event.

        Returns:
            None
        """
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return

        plan = self._container.get_plan()
        if plan.services != self._pebble_layer.services:
            self.unit.status = MaintenanceStatus(
                f"Configuring pebble layer for {self._service_name}"
            )
            self._container.add_layer(self._container_name, self._pebble_layer, combine=True)
            self._container.restart(self._service_name)
            logger.info(f"Restarted container {self._service_name}")
            self.unit.status = ActiveStatus()

    def _on_certificate_available(self, event: CertificateAvailableEvent) -> None:
        """Triggered when controller certificate is available.

        Args:
            event (CertificateAvailableEvent): Juju event

        Returns:
            None
        """
        logger.info("Controller certificate available")
        if not self._container.can_connect():
            logger.info("Can't connect to container - Deferring")
            event.defer()
            return
        self._container.push(
            path=f"{self.BASE_NGINX_PATH}/nms_nginx.pem", source=event.certificate
        )
        self._container.push(
            path=f"{self.BASE_NGINX_PATH}/nms_nginx.key.pem", source=event.private_key
        )
        self._on_magma_nms_nginx_proxy_pebble_ready(event)


if __name__ == "__main__":
    main(MagmaNmsNginxProxyCharm)
