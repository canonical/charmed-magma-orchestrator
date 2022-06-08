#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from charms.tls_certificates_interface.v0.tls_certificates import (
    InsecureCertificatesRequires,
)
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer

logger = logging.getLogger(__name__)


class MagmaNmsNginxProxyCharm(CharmBase):
    BASE_NGINX_PATH = "/etc/nginx/conf.d"
    NGINX_CONFIG_FILE_NAME = "nginx_proxy_ssl.conf"

    def __init__(self, *args):
        super().__init__(*args)
        self._container_name = self._service_name = "magma-nms-nginx-proxy"
        self._container = self.unit.get_container(self._container_name)
        self.certificates = InsecureCertificatesRequires(self, "certificates")
        self.service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[("https", 443)],
            service_type="LoadBalancer",
            service_name="nginx-proxy",
            additional_labels={"app.kubernetes.io/part-of": "magma"},
        )
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(
            self.on.magma_nms_nginx_proxy_pebble_ready, self._on_magma_nms_nginx_proxy_pebble_ready
        )
        self.framework.observe(
            self.on.certificates_relation_joined, self._on_certificates_relation_joined
        )
        self.framework.observe(
            self.certificates.on.certificate_available, self._on_certificate_available
        )

    def _on_install(self, event):
        if not self._container.can_connect():
            event.defer()
            return
        self._write_nginx_config_file()

    def _write_nginx_config_file(self):
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

    def _on_certificates_relation_joined(self, event):
        domain_name = self.model.config.get("domain")
        if not self._domain_config_is_valid:
            logger.info("Domain config is not valid")
            event.defer()
            return
        self.certificates.request_certificate(
            cert_type="server",
            common_name=domain_name,  # type: ignore[arg-type]
        )

    def _on_certificate_available(self, event):
        logger.info("Certificate is available")
        if not self._container.can_connect():
            logger.info("Cant connect to container - Won't push certificates to workload")
            event.defer()
            return
        if self._certs_are_stored:
            logger.info("Certificates are already stored - Doing nothing")
            return
        certificate_data = event.certificate_data
        if certificate_data["common_name"] == self.model.config["domain"]:
            logger.info("Pushing certificate to workload")
            self._container.push(
                path=f"{self.BASE_NGINX_PATH}/nms_nginx.pem",
                source=certificate_data["cert"],
            )
            self._container.push(
                path=f"{self.BASE_NGINX_PATH}/nms_nginx.key.pem",
                source=certificate_data["key"],
            )
            self._on_magma_nms_nginx_proxy_pebble_ready(event)

    @property
    def _certs_are_stored(self) -> bool:
        return self._container.exists(f"{self.BASE_NGINX_PATH}/nms_nginx.pem") and \
               self._container.exists(f"{self.BASE_NGINX_PATH}/nms_nginx.key.pem")

    @property
    def _nginx_config_file_is_stored(self) -> bool:
        return self._container.exists(f"{self.BASE_NGINX_PATH}/{self.NGINX_CONFIG_FILE_NAME}")

    def _on_magma_nms_nginx_proxy_pebble_ready(self, event):
        """Configures magma-nms-nginx-proxy pebble layer."""
        if not self._domain_config_is_valid:
            self.unit.status = BlockedStatus("Config 'domain' is not valid")
            event.defer()
            return
        if not self._magmalte_relation_created:
            self.unit.status = BlockedStatus("Waiting for magmalte relation to be created")
            event.defer()
            return
        if not self._certificates_relation_created:
            self.unit.status = BlockedStatus("Waiting for certificates relation to be created")
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

    def _configure_pebble(self, event):
        if self._container.can_connect():
            plan = self._container.get_plan()
            if plan.services != self._pebble_layer.services:
                self.unit.status = MaintenanceStatus(
                    f"Configuring pebble layer for {self._service_name}..."
                )
                self._container.add_layer(self._container_name, self._pebble_layer, combine=True)
                self._container.restart(self._service_name)
                logger.info(f"Restarted container {self._service_name}")
                self.unit.status = ActiveStatus()
        else:
            self.unit.status = WaitingStatus("Waiting for container to be ready...")
            event.defer()

    def _relation_created(self, relation_name: str) -> bool:
        if not self.model.get_relation(relation_name):
            return False
        return True

    @property
    def _certificates_relation_created(self) -> bool:
        return self._relation_created("certificates")

    @property
    def _magmalte_relation_created(self) -> bool:
        return self._relation_created("magmalte")

    @property
    def _pebble_layer(self) -> Layer:
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

    @property
    def _domain_config_is_valid(self) -> bool:
        domain = self.model.config.get("domain")
        if not domain:
            return False
        return True


if __name__ == "__main__":
    main(MagmaNmsNginxProxyCharm)
