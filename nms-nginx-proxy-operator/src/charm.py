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
from ops.charm import (
    CharmBase,
    PebbleReadyEvent,
    RelationChangedEvent,
    RelationJoinedEvent,
)
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import ExecError, Layer

logger = logging.getLogger(__name__)


class MagmaNmsNginxProxyCharm(CharmBase):
    """Main class that is instantiated everytime an event occurs."""

    BASE_NGINX_PATH = "/etc/nginx/conf.d"
    NGINX_CONFIG_FILE_NAME = "nginx_proxy_ssl.conf"
    NGINX_HTTPS_PORT = 443

    def __init__(self, *args):
        """Initializes all events that need to be observed."""
        super().__init__(*args)
        self._container_name = self._service_name = "magma-nms-nginx-proxy"
        self._container = self.unit.get_container(self._container_name)
        self.cert_controller = CertControllerRequires(self, "cert-controller")
        self.service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[ServicePort(name="https", port=self.NGINX_HTTPS_PORT)],
            service_type="LoadBalancer",
            service_name="nginx-proxy",
            additional_labels={"app.kubernetes.io/part-of": "magma"},
        )

        self.framework.observe(
            self.on.magma_nms_nginx_proxy_pebble_ready, self._on_magma_nms_nginx_proxy_pebble_ready
        )
        self.framework.observe(
            self.on.magma_nms_magmalte_relation_joined,
            self._push_nginx_config_file_to_workload,
        )
        self.framework.observe(
            self.on.magma_nms_magmalte_relation_changed,
            self._push_nginx_config_file_to_workload,
        )
        self.framework.observe(
            self.cert_controller.on.certificate_available, self._on_certificate_available
        )

    def _on_magma_nms_nginx_proxy_pebble_ready(
        self, event: Union[PebbleReadyEvent, CertificateAvailableEvent]
    ) -> None:
        """Configures magma-nms-nginx-proxy pebble layer.

        Args:
            event: Juju event
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

    def _on_certificate_available(self, event: CertificateAvailableEvent) -> None:
        """Triggered when controller certificate is available.

        Args:
            event (CertificateAvailableEvent): Juju event
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

    def _push_nginx_config_file_to_workload(
        self, event: Union[RelationChangedEvent, RelationJoinedEvent]
    ) -> None:
        """Triggered on `nms-magmalte` relation events.

        Writes nginx config file to workload container.

        Args:
            event: Juju event (RelationChangedEvent or RelationJoinedEvent)
        """
        magmalte_relation = event.relation
        units = magmalte_relation.units
        try:
            magmalte_service_name = magmalte_relation.data[next(iter(units))]["k8s_service_name"]
            magmalte_service_port = magmalte_relation.data[next(iter(units))]["k8s_service_port"]
        except KeyError:
            logger.info("Magmalte service details not available. Deferring event.")
            event.defer()
            return
        if not self._container.can_connect():
            logger.info("Can't connect to container. Deferring event.")
            event.defer()
            return
        config_file = (
            "server {\n"
            f"listen {self.NGINX_HTTPS_PORT};\n"
            "ssl on;\n"
            f"ssl_certificate {self.BASE_NGINX_PATH}/nms_nginx.pem;\n"
            f"ssl_certificate_key {self.BASE_NGINX_PATH}/nms_nginx.key.pem;\n"
            "location / {\n"
            f"proxy_pass http://{magmalte_service_name}:{magmalte_service_port};\n"
            "proxy_set_header Host $http_host;\n"
            "proxy_set_header X-Forwarded-Proto $scheme;\n"
            "}\n"
            "}"
        )
        self._container.push(
            path=f"{self.BASE_NGINX_PATH}/{self.NGINX_CONFIG_FILE_NAME}", source=config_file
        )

    def _configure_pebble(self, event: Union[PebbleReadyEvent, CertificateAvailableEvent]) -> None:
        """Configures Pebble layer.

        Creates nginx service and starts it.

        Args:
            event: Juju event.
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
        # TODO: _reload_nginx() is needed by the workaround for not working container.restart()
        #       and should be removed as soon as the proper Juju mechanism works as expected.
        self._reload_nginx()
        logger.info(f"Restarted service {self._service_name}")
        self.unit.status = ActiveStatus()

    def _reload_nginx(self) -> None:
        """Reloads the nginx process."""
        nginx_master_pid, _ = self._container.exec(["cat", "/var/run/nginx.pid"]).wait_output()
        self._container.exec(["/bin/bash", "-c", "kill", "-HUP", f"{nginx_master_pid.strip()}"])
        logger.info(f"Reloaded process with pid {nginx_master_pid.strip()}")

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
            bool: Whether the `magmalte` relation is created
        """
        return self._relation_created("magma-nms-magmalte")

    @property
    def _certs_are_stored(self) -> bool:
        """Checks whether the nginx certs are stored.

        Returns:
            bool: Whether the nginx certs are stored
        """
        return self._container.exists(
            f"{self.BASE_NGINX_PATH}/nms_nginx.pem"
        ) and self._container.exists(f"{self.BASE_NGINX_PATH}/nms_nginx.key.pem")

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


class ProcessExecutionError(Exception):
    """Custom error improving logging in case of ExecError."""

    def __init__(self, error: ExecError):
        """Print error details.

        Args:
            error (ExecError): Original error
        """
        logger.error(f"ERROR: Process exited with code {error.exit_code}.")
        if error.stderr:
            logger.error("Stderr:")
            for line in error.stderr.splitlines():
                logger.error(f"    {str(line)}")


if __name__ == "__main__":
    main(MagmaNmsNginxProxyCharm)
