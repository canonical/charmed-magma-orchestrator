#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from typing import List

from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from httpx import HTTPStatusError
from lightkube import Client
from lightkube.models.core_v1 import (
    SecretVolumeSource,
    ServicePort,
    ServiceSpec,
    Volume,
    VolumeMount,
)
from lightkube.models.meta_v1 import ObjectMeta
from lightkube.resources.apps_v1 import StatefulSet
from lightkube.resources.core_v1 import Service
from ops.charm import CharmBase, PebbleReadyEvent, RelationChangedEvent, RemoveEvent
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer

logger = logging.getLogger(__name__)


class MagmaOrc8rNginxCharm(CharmBase):

    REQUIRED_RELATIONS = [
        "magma-orc8r-bootstrapper",
        "magma-orc8r-certifier",
        "magma-orc8r-obsidian",
    ]

    def __init__(self, *args):
        super().__init__(*args)
        self._container_name = self._service_name = "magma-orc8r-nginx"
        self._container = self.unit.get_container(self._container_name)
        self.framework.observe(
            self.on.magma_orc8r_nginx_pebble_ready, self._on_magma_orc8r_nginx_pebble_ready
        )
        self.framework.observe(
            self.on.magma_orc8r_certifier_relation_changed,
            self._on_magma_orc8r_certifier_relation_changed,
        )
        self.framework.observe(self.on.remove, self._on_remove)
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

    def _on_magma_orc8r_nginx_pebble_ready(self, event: PebbleReadyEvent):
        if not self._relations_created:
            event.defer()
            return
        if not self._relations_ready:
            event.defer()
            return
        if not self._get_domain_name:
            self.unit.status = WaitingStatus(
                "Waiting for magma-orc8r-certifier relation to be ready"
            )
            event.defer()
            return
        self._create_additional_orc8r_nginx_services()
        self._configure_pebble_layer(event)

    def _on_magma_orc8r_certifier_relation_changed(self, event: RelationChangedEvent):
        """Mounts certificates required by the nms-magmalte."""
        if not self._orc8r_certs_mounted:
            self.unit.status = MaintenanceStatus("Mounting NMS certificates")
            self._mount_certifier_certs()

    def _mount_certifier_certs(self) -> None:
        """Patch the StatefulSet to include certifier certs secret mount."""
        self.unit.status = MaintenanceStatus(
            "Mounting additional volumes required by the magma-orc8r-nginx container"
        )
        client = Client()
        stateful_set = client.get(StatefulSet, name=self.app.name, namespace=self._namespace)
        stateful_set.spec.template.spec.volumes.extend(self._magma_orc8r_nginx_volumes)  # type: ignore[attr-defined]  # noqa: E501
        stateful_set.spec.template.spec.containers[1].volumeMounts.extend(  # type: ignore[attr-defined]  # noqa: E501
            self._magma_orc8r_nginx_volume_mounts
        )
        client.patch(StatefulSet, name=self.app.name, obj=stateful_set, namespace=self._namespace)
        logger.info("Additional K8s resources for magma-orc8r-nginx container applied!")

    def _configure_pebble_layer(self, event: PebbleReadyEvent):
        self.unit.status = MaintenanceStatus(f"Configuring pebble layer for {self._service_name}")
        pebble_layer = self._pebble_layer
        if self._container.can_connect():
            plan = self._container.get_plan()
            if plan.services != pebble_layer.services:
                self._generate_nginx_config()
                self._container.add_layer(self._container_name, pebble_layer, combine=True)
                self._container.restart(self._service_name)
                logger.info(f"Restarted container {self._service_name}")
                self.unit.status = ActiveStatus()
        else:
            self.unit.status = WaitingStatus(f"Waiting for {self._container} to be ready")
            event.defer()
            return

    def _generate_nginx_config(self):
        """Generates nginx config to /etc/nginx/nginx.conf."""
        logger.info("Generating nginx config file...")
        process = self._container.exec(
            command=["/usr/local/bin/generate_nginx_configs.py"],
            environment={
                "PROXY_BACKENDS": f"{self._namespace}.svc.cluster.local",
                "CONTROLLER_HOSTNAME": f"controller.{self._get_domain_name}",
                "RESOLVER": "kube-dns.kube-system.svc.cluster.local valid=10s",
                "SERVICE_REGISTRY_MODE": "k8s",
                "SSL_CERTIFICATE": "/var/opt/magma/certs/controller.crt",
                "SSL_CERTIFICATE_KEY": "/var/opt/magma/certs/controller.key",
                "SSL_CLIENT_CERTIFICATE": "/var/opt/magma/certs/certifier.pem",
            },
        )
        stdout, _ = process.wait_output()
        logger.info(stdout)

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

    def _on_remove(self, event: RemoveEvent):
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
    def _magma_orc8r_nginx_volumes(self) -> List[Volume]:
        """Returns the additional volumes required by the magma-orc8r-nginx."""
        return [
            Volume(
                name="certs",
                secret=SecretVolumeSource(secretName="orc8r-certs"),
            ),
        ]

    @property
    def _magma_orc8r_nginx_volume_mounts(self) -> List[VolumeMount]:
        """Returns the additional volume mounts for the magma-orc8r-nginx container."""
        return [
            VolumeMount(
                mountPath="/var/opt/magma/certs",
                name="certs",
            ),
        ]

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
                            nodePort=31200,
                        ),
                        ServicePort(
                            name="open-legacy",
                            port=443,
                            targetPort=8444,
                            nodePort=30747,
                        ),
                        ServicePort(
                            name="open",
                            port=8444,
                            targetPort=8444,
                            nodePort=30618,
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
    def _relations_created(self) -> bool:
        if missing_relations := [
            relation
            for relation in self.REQUIRED_RELATIONS
            if not self.model.get_relation(relation)
        ]:
            msg = f"Waiting for relation(s) to be created: {', '.join(missing_relations)}"
            self.unit.status = BlockedStatus(msg)
            return False
        return True

    @property
    def _relations_ready(self) -> bool:
        """Checks whether required relations are ready."""
        not_ready_relations = [
            relation for relation in self.REQUIRED_RELATIONS if not self._relation_active(relation)
        ]
        if not_ready_relations:
            msg = f"Waiting for relation(s) to be ready: {', '.join(not_ready_relations)}"
            self.unit.status = WaitingStatus(msg)
            return False
        return True

    def _relation_active(self, relation_name: str) -> bool:
        try:
            rel = self.model.get_relation(relation_name)
            units = rel.units  # type: ignore[union-attr]
            return rel.data[next(iter(units))]["active"] == "True"  # type: ignore[union-attr]
        except (AttributeError, KeyError, StopIteration):
            return False

    def _orc8r_nginx_service_created(self, service_name: str) -> bool:
        """Checks whether given K8s service exists or not."""
        client = Client()
        try:
            client.get(Service, name=service_name, namespace=self._namespace)
            return True
        except HTTPStatusError:
            return False

    @property
    def _orc8r_certs_mounted(self) -> bool:
        """Check to see if the NMS certs have already been mounted."""
        client = Client()
        statefulset = client.get(StatefulSet, name=self.app.name, namespace=self._namespace)
        return all(
            volume_mount in statefulset.spec.template.spec.containers[1].volumeMounts  # type: ignore[attr-defined]  # noqa: E501
            for volume_mount in self._magma_orc8r_nginx_volume_mounts
        )

    @property
    def _get_domain_name(self):
        """Gets domain name for the data bucket sent by certifier relation."""
<<<<<<< HEAD
        try:
            certifier_relation = self.model.get_relation("magma-orc8r-certifier")
            units = certifier_relation.units  # type: ignore[union-attr]
            return certifier_relation.data[next(iter(units))]["domain"]  # type: ignore[union-attr]
        except (AttributeError, KeyError, StopIteration):
=======
        certifier_relation = self.model.get_relation("certifier")
        units = certifier_relation.units  # type: ignore[union-attr]
        try:
            return certifier_relation.data[next(iter(units))]["domain"]  # type: ignore[union-attr]
        except KeyError:
>>>>>>> fixes tox static analysis issues
            return None

    @property
    def _namespace(self) -> str:
        return self.model.name


if __name__ == "__main__":
    main(MagmaOrc8rNginxCharm)
