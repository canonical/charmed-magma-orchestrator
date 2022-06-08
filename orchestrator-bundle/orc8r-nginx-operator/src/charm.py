#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from typing import List

from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch

from charms.magma_orc8r_certifier.v0.cert_certifier import CertCertifierRequires
from charms.magma_orc8r_certifier.v0.cert_controller import CertControllerRequires
from httpx import HTTPStatusError
from lightkube import Client
from lightkube.models.core_v1 import ServicePort, ServiceSpec
from lightkube.models.meta_v1 import ObjectMeta
from lightkube.resources.core_v1 import Service
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import ExecError, Layer

logger = logging.getLogger(__name__)


class MagmaOrc8rNginxCharm(CharmBase):
    # TODO: the generate_nginx_configs.py requires the service_registry.yml config file. It should
    # TODO: also use persistent storage

    BASE_CERTS_PATH = "/var/opt/magma/certs"

    def __init__(self, *args):
        super().__init__(*args)
        self._certifier_cert = CertCertifierRequires(self, "cert-certifier")
        self._controller_cert = CertControllerRequires(self, "cert-controller")
        self._container_name = self._service_name = "magma-orc8r-nginx"
        self._container = self.unit.get_container(self._container_name)
        self.service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[
                ("health", 80),
                ("clientcert", 8443),
                ("open", 8444),
                ("api", 443, 9443),
            ],
            service_type="LoadBalancer",
            service_name="orc8r-nginx-proxy",
            additional_labels={"app.kubernetes.io/part-of": "orc8r"},
            additional_selectors={"app.kubernetes.io/name": "orc8r-nginx"},
        )
        self.framework.observe(
            self.on.magma_orc8r_nginx_pebble_ready, self._on_magma_orc8r_nginx_pebble_ready
        )
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.remove, self._on_remove)
        self.framework.observe(
            self._certifier_cert.on.certificate_available, self._on_certifier_certificate_available
        )
        self.framework.observe(
            self._controller_cert.on.certificate_available, self._on_controller_certificate_available
        )

    def _on_certifier_certificate_available(self, event):
        logger.info("Certifier certificate available")
        if not self._container.can_connect():
            logger.info("Can't connect to container - Deferring")
            event.defer()
            return
        self._container.push(
            path=f"{self.BASE_CERTS_PATH}/certifier.pem", source=event.certificate
        )
        self._on_magma_orc8r_nginx_pebble_ready(event)

    def _on_controller_certificate_available(self, event):
        logger.info("Controller certificate available")
        if not self._container.can_connect():
            logger.info("Can't connect to container - Deferring")
            event.defer()
            return
        self._container.push(
            path=f"{self.BASE_CERTS_PATH}/controller.crt", source=event.certificate
        )
        self._container.push(
            path=f"{self.BASE_CERTS_PATH}/controller.key", source=event.private_key
        )
        self._on_magma_orc8r_nginx_pebble_ready(event)

    def _on_install(self, event):
        self._generate_nginx_config()
        self._create_additional_orc8r_nginx_services()

    def _on_magma_orc8r_nginx_pebble_ready(self, event):
        if not self._relations_ready:
            event.defer()
            return
        if not self._domain_config_is_valid:
            logger.info("Domain config is not valid")
            event.defer()
            return
        if not self._certs_are_stored:
            logger.info("Certs are not yet available")
            event.defer()
            return
        self._configure_pebble_layer(event)

    def _configure_pebble_layer(self, event):
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

    def _generate_nginx_config(self):
        """Generates nginx config to /etc/nginx/nginx.conf."""
        logger.info("Generating nginx config file...")
        domain_name = self.model.config.get("domain")
        process = self._container.exec(
            command=["/usr/local/bin/generate_nginx_configs.py"],
            environment={
                "PROXY_BACKENDS": f"{self._namespace}.svc.cluster.local",
                "CONTROLLER_HOSTNAME": f"controller.{domain_name}",
                "RESOLVER": "kube-dns.kube-system.svc.cluster.local valid=10s",
                "SERVICE_REGISTRY_MODE": "k8s",
            },
        )
        try:
            process.wait_output()
        except ExecError as e:
            logger.error("Exited with code %d. Stderr:", e.exit_code)
            for line in e.stderr.splitlines():
                logger.error("    %s", line)
            raise e
        logger.info("Successfully generated nginx config file")

    def _create_additional_orc8r_nginx_services(self):
        """Creates additional K8s services which are expected to be delivered by the
        magma-orc8r-nginx.
        """
        client = Client()
        logger.info("Creating additional magma-orc8r-nginx services...")
        for service in self._magma_orc8r_nginx_additional_services:
            if not self._orc8r_nginx_service_created(service.metadata.name):
                logger.info(f"Creating {service.metadata.name} service...")
                client.create(service)

    def _on_remove(self, event):
        """Remove additional magma-orc8r-nginx services."""
        client = Client()
        for service in self._magma_orc8r_nginx_additional_services:
            client.delete(Service, name=service.metadata.name, namespace=self._namespace)

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
                        "environment": {
                            "SERVICE_REGISTRY_MODE": "k8s",
                            "SERVICE_REGISTRY_NAMESPACE": self._namespace,
                        },
                    }
                },
            }
        )

    @property
    def _magma_orc8r_nginx_additional_services(self) -> List[Service]:
        """Returns list of additional K8s services to be created by magma-orc8r-nginx."""
        return [
            Service(
                apiVersion="v1",
                kind="Service",
                metadata=ObjectMeta(
                    namespace=self._namespace,
                    name="orc8r-bootstrap-nginx",
                    labels={
                        "app.kubernetes.io/component": "nginx-proxy",
                        "app.kubernetes.io/part-of": "orc8r",
                    },
                ),
                spec=ServiceSpec(
                    selector={
                        "app.kubernetes.io/name": "orc8r-nginx",
                    },
                    ports=[
                        ServicePort(
                            name="health",
                            port=80,
                            targetPort=80,
                        ),
                        ServicePort(
                            name="open-legacy",
                            port=443,
                            targetPort=8444,
                        ),
                        ServicePort(
                            name="open",
                            port=8444,
                            targetPort=8444,
                        ),
                    ],
                    type="LoadBalancer",
                ),
            ),
            Service(
                apiVersion="v1",
                kind="Service",
                metadata=ObjectMeta(
                    namespace=self._namespace,
                    name="orc8r-clientcert-nginx",
                    labels={
                        "app.kubernetes.io/component": "nginx-proxy",
                        "app.kubernetes.io/part-of": "orc8r",
                    },
                ),
                spec=ServiceSpec(
                    selector={"app.kubernetes.io/name": "orc8r-nginx"},
                    ports=[
                        ServicePort(
                            name="health",
                            port=80,
                            targetPort=80,
                        ),
                        ServicePort(
                            name="clientcert-legacy",
                            port=443,
                            targetPort=8443,
                        ),
                        ServicePort(
                            name="clientcert",
                            port=8443,
                            targetPort=8443,
                        ),
                    ],
                    type="LoadBalancer",
                ),
            ),
        ]

    @property
    def _relations_ready(self) -> bool:
        """Checks whether required relations are ready."""
        required_relations = ["bootstrapper", "obsidian", "cert-certifier", "cert-controller"]
        missing_relations = [
            relation
            for relation in required_relations
            if not self.model.get_relation(relation)
            or len(self.model.get_relation(relation).units) == 0  # type: ignore[union-attr]  # noqa: W503, E501
        ]
        if missing_relations:
            msg = f"Waiting for relations: {', '.join(missing_relations)}"
            self.unit.status = BlockedStatus(msg)
            return False
        return True

    def _orc8r_nginx_service_created(self, service_name) -> bool:
        """Checks whether given K8s service exists or not."""
        client = Client()
        try:
            client.get(Service, name=service_name, namespace=self._namespace)
            return True
        except HTTPStatusError:
            return False

    @property
    def _namespace(self) -> str:
        return self.model.name

    @property
    def _domain_config_is_valid(self) -> bool:
        domain = self.model.config.get("domain")
        if not domain:
            return False
        return True

    @property
    def _certs_are_stored(self) -> bool:
        return (
            self._container.exists(f"{self.BASE_CERTS_PATH}/controller.crt")
            and self._container.exists(f"{self.BASE_CERTS_PATH}/controller.key")  # noqa: W503
            and self._container.exists(f"{self.BASE_CERTS_PATH}/certifier.pem")  # noqa: W503
        )


if __name__ == "__main__":
    main(MagmaOrc8rNginxCharm)
