#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from charms.tls_certificates_interface.v0.tls_certificates import (
    CertificatesRequirerCharmEvents,
    InsecureCertificatesRequires,
)
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer

logger = logging.getLogger(__name__)


class MagmaOrc8rBootstrapperCharm(CharmBase):

    CERTIFICATE_DIRECTORY = "/var/opt/magma/certs"
    CERTIFICATE_COMMON_NAME = "whatever.domain"  # Not used
    CERTIFICATE_NAME = "bootstrapper.key"

    on = CertificatesRequirerCharmEvents()

    def __init__(self, *args):
        super().__init__(*args)
        self._container_name = self._service_name = "magma-orc8r-bootstrapper"
        self._container = self.unit.get_container(self._container_name)
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[("grpc", 9180, 9088)],
            additional_labels={"app.kubernetes.io/part-of": "orc8r-app"},
        )
        self.certificates = InsecureCertificatesRequires(self, "certificates")
        self.framework.observe(
            self.on.magma_orc8r_bootstrapper_pebble_ready,
            self._on_magma_orc8r_bootstrapper_pebble_ready,
        )
        self.framework.observe(
            self.on.certificates_relation_joined, self._on_certificates_relation_joined
        )
        self.framework.observe(self.on.certificate_available, self._on_certificate_available)

    def _on_certificates_relation_joined(self, event):
        self.certificates.request_certificate(
            cert_type="server",
            common_name=self.CERTIFICATE_COMMON_NAME,
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
        if certificate_data["common_name"] == self.CERTIFICATE_COMMON_NAME:
            logger.info("Pushing certificate to workload")
            self._container.push(
                path=f"{self.CERTIFICATE_DIRECTORY}/{self.CERTIFICATE_NAME}",
                source=certificate_data["key"],
            )
            self._on_magma_orc8r_bootstrapper_pebble_ready(event)

    @property
    def _certs_are_stored(self) -> bool:
        return self._container.exists(f"{self.CERTIFICATE_DIRECTORY}/{self.CERTIFICATE_NAME}")

    def _on_magma_orc8r_bootstrapper_pebble_ready(self, event):
        """Triggered when pebble is ready."""
        if not self._certificates_relation_ready:
            self.unit.status = BlockedStatus("Waiting for certificates relation")
            event.defer()
            return
        if not self._certs_are_stored:
            self.unit.status = WaitingStatus("Waiting for certs to be available")
            event.defer()
            return
        self._configure_pebble(event)

    def _configure_pebble(self, event):
        """Adds layer to pebble config if the proposed config is different from the current one."""
        if self._container.can_connect():
            plan = self._container.get_plan()
            layer = self._pebble_layer
            if plan.services != layer.services:
                self.unit.status = MaintenanceStatus(
                    f"Configuring pebble layer for {self._service_name}"
                )
                self._container.add_layer(self._container_name, layer, combine=True)
                self._container.restart(self._service_name)
                logger.info(f"Restarted container {self._service_name}")
                self.unit.status = ActiveStatus()
        else:
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()

    @property
    def _certificates_relation_ready(self) -> bool:
        """Checks whether certificates relation is ready."""
        certificates_relation = self.model.get_relation("certificates")
        if not certificates_relation or len(certificates_relation.units) == 0:
            return False
        return True

    @property
    def _pebble_layer(self) -> Layer:
        return Layer(
            {
                "summary": f"{self._service_name} pebble layer",
                "services": {
                    self._service_name: {
                        "override": "replace",
                        "startup": "enabled",
                        "command": "/usr/bin/envdir "
                        "/var/opt/magma/envdir "
                        "/var/opt/magma/bin/bootstrapper "
                        "-cak=/var/opt/magma/certs/bootstrapper.key "
                        "-logtostderr=true "
                        "-v=0",
                        "environment": {
                            "SERVICE_REGISTRY_MODE": "k8s",
                            "SERVICE_REGISTRY_NAMESPACE": self._namespace,
                        },
                    }
                },
            }
        )

    @property
    def _namespace(self) -> str:
        return self.model.name


if __name__ == "__main__":
    main(MagmaOrc8rBootstrapperCharm)
