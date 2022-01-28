#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from typing import List

import httpx
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from lightkube import Client, codecs
from lightkube.core.exceptions import ApiError
from lightkube.models.core_v1 import (
    ConfigMapVolumeSource,
    SecretVolumeSource,
    Volume,
    VolumeMount,
)
from lightkube.resources.apps_v1 import StatefulSet
from lightkube.resources.core_v1 import ConfigMap
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from ops.pebble import Layer

logger = logging.getLogger(__name__)


class MagmaNmsNginxProxyCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self._container_name = self._service_name = "magma-nms-nginx-proxy"
        self._container = self.unit.get_container(self._container_name)
        self._context = {"namespace": self._namespace, "app_name": self.app.name}
        self.framework.observe(
            self.on.magma_nms_nginx_proxy_pebble_ready, self._on_magma_nms_nginx_proxy_pebble_ready
        )
        self.framework.observe(self.on.certifier_relation_changed, self._configure_nginx)
        self.framework.observe(self.on.remove, self._on_remove)
        self.service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[("https", 443, 443, 30760)],
            service_type="LoadBalancer",
            service_name="nginx-proxy",
            additional_labels={"app.kubernetes.io/part-of": "magma"},
        )

    def _on_magma_nms_nginx_proxy_pebble_ready(self, event):
        """Configures magma-nms-nginx-proxy pebble layer."""
        if not self._relations_ready:
            event.defer()
            return
        self._configure_pebble()

    def _configure_pebble(self):
        self.unit.status = MaintenanceStatus(
            f"Configuring pebble layer for {self._service_name}..."
        )
        plan = self._container.get_plan()
        if plan.services != self._pebble_layer.services:
            self._container.add_layer(self._container_name, self._pebble_layer, combine=True)
            self._container.restart(self._service_name)
            logger.info(f"Restarted container {self._service_name}")
            self.unit.status = ActiveStatus()

    def _configure_nginx(self, event):
        if not self._nms_certs_mounted:
            self.unit.status = MaintenanceStatus("Mounting NMS certificates...")
            self._mount_certifier_certs()
        if not self._nginx_proxy_etc_configmap_created:
            self.unit.status = MaintenanceStatus("Creating required Kubernetes resources...")
            self._create_magma_nms_nginx_proxy_configmap()

    def _create_magma_nms_nginx_proxy_configmap(self) -> bool:
        """Creates ConfigMap required by the magma-nms-nginx-proxy."""
        client = Client()
        with open("src/templates/config_map.yaml.j2") as configmap_manifest:
            config_map = codecs.load_all_yaml(configmap_manifest, context=self._context)[0]
            try:
                client.create(config_map)
            except ApiError as e:
                logger.debug("Failed to create ConfigMap: %s.", str(config_map.to_dict()))
                raise e
        return True

    def _mount_certifier_certs(self) -> None:
        """Patch the StatefulSet to include NMS certs secret mount."""
        self.unit.status = MaintenanceStatus(
            "Mounting additional volumes required by the magma-nms-nginx-proxy container..."
        )
        client = Client()
        try:
            stateful_set = client.get(StatefulSet, name=self.app.name, namespace=self._namespace)
            stateful_set.spec.template.spec.volumes.extend(self._magma_nms_nginx_proxy_volumes)  # type: ignore[attr-defined]  # noqa: E501
            stateful_set.spec.template.spec.containers[1].volumeMounts.extend(  # type: ignore[attr-defined]  # noqa: E501
                self._magma_nms_nginx_proxy_volume_mounts
            )
            client.patch(
                StatefulSet, name=self.app.name, obj=stateful_set, namespace=self._namespace
            )
        except ApiError as e:
            logger.debug(
                "Failed to mount additional volumes required by the magma-nms-nginx-proxy "
                "container!"
            )
            raise e
        logger.info("Additional K8s resources for magma-nms-nginx-proxy container applied!")

    @property
    def _relations_ready(self) -> bool:
        """Checks whether required relations are ready."""
        required_relations = ["certifier", "magmalte"]
        missing_relations = [
            relation for relation in required_relations if not self.model.get_relation(relation)
        ]
        if missing_relations:
            msg = f"Waiting for relations: {', '.join(missing_relations)}"
            self.unit.status = BlockedStatus(msg)
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
                        "command": "nginx",
                    }
                },
            }
        )

    @property
    def _magma_nms_nginx_proxy_volumes(self) -> List[Volume]:
        """Returns a list of volumes required by the magma-nms-nginx-proxy container"""
        return [
            Volume(
                name="orc8r-secrets-certs",
                secret=SecretVolumeSource(secretName="nms-certs"),
            ),
            Volume(
                name="nginx-proxy-etc",
                configMap=ConfigMapVolumeSource(name="nginx-proxy-etc"),
            ),
        ]

    @property
    def _magma_nms_nginx_proxy_volume_mounts(self) -> List[VolumeMount]:
        """Returns a list of volume mounts required by the magma-nms-nginx-proxy container"""
        return [
            VolumeMount(
                mountPath="/etc/nginx/conf.d/nginx_proxy_ssl.conf",
                name="nginx-proxy-etc",
                subPath="nginx_proxy_ssl.conf",
            ),
            VolumeMount(
                mountPath="/etc/nginx/conf.d/nms_nginx.pem",
                name="orc8r-secrets-certs",
                readOnly=True,
                subPath="controller.crt",
            ),
            VolumeMount(
                mountPath="/etc/nginx/conf.d/nms_nginx.key.pem",
                name="orc8r-secrets-certs",
                readOnly=True,
                subPath="controller.key",
            ),
        ]

    @property
    def _nms_certs_mounted(self) -> bool:
        """Check to see if the NMS certs have already been mounted."""
        client = Client()
        statefulset = client.get(StatefulSet, name=self.app.name, namespace=self._namespace)
        return all(
            volume_mount in statefulset.spec.template.spec.containers[1].volumeMounts  # type: ignore[attr-defined]  # noqa: E501
            for volume_mount in self._magma_nms_nginx_proxy_volume_mounts
        )

    @property
    def _nginx_proxy_etc_configmap_created(self) -> bool:
        """Check to see if the nginx-proxy-etc have already been created."""
        client = Client()
        try:
            client.get(ConfigMap, name="nginx-proxy-etc", namespace=self._namespace)
            return True
        except httpx.HTTPError:
            return False

    def _on_remove(self, event):
        client = Client()
        client.delete(ConfigMap, name="nginx-proxy-etc", namespace=self._namespace)

    @property
    def _namespace(self) -> str:
        return self.model.name


if __name__ == "__main__":
    main(MagmaNmsNginxProxyCharm)
