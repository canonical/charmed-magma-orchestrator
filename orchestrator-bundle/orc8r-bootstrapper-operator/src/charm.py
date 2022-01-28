#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from lightkube import Client
from lightkube.core.exceptions import ApiError
from lightkube.models.core_v1 import SecretVolumeSource, Volume, VolumeMount
from lightkube.resources.apps_v1 import StatefulSet
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus
from ops.pebble import ConnectionError, Layer

logger = logging.getLogger(__name__)


class MagmaOrc8rBootstrapperCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self._container_name = self._service_name = "magma-orc8r-bootstrapper"
        self._container = self.unit.get_container(self._container_name)
        self.framework.observe(
            self.on.magma_orc8r_bootstrapper_pebble_ready,
            self._on_magma_orc8r_bootstrapper_pebble_ready,
        )
        self.framework.observe(
            self.on.certifier_relation_joined, self._on_certifier_relation_joined
        )
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[("grpc", 9180, 9088)],
            additional_labels={"app.kubernetes.io/part-of": "orc8r-app"},
        )

    def _on_magma_orc8r_bootstrapper_pebble_ready(self, event):
        """Triggered when pebble is ready."""
        if not self._certifier_relation_ready:
            self.unit.status = BlockedStatus("Waiting for orc8r-certifier relation...")
            event.defer()
            return
        self._configure_pebble(event)

    def _on_certifier_relation_joined(self, event):
        if not self._orc8r_certs_mounted:
            self.unit.status = MaintenanceStatus("Mounting certificates from orc8r-certifier...")
            self._mount_orc8r_certs()

    def _configure_pebble(self, event):
        """Adds layer to pebble config if the proposed config is different from the current one."""
        pebble_layer = self._pebble_layer
        try:
            plan = self._container.get_plan()
            if plan.services != pebble_layer.services:
                self._container.add_layer(self._container_name, pebble_layer, combine=True)
                self._container.restart(self._service_name)
                logger.info(f"Restarted container {self._service_name}")
                self.unit.status = ActiveStatus()
        except ConnectionError:
            logger.error(
                f"Could not restart {self._service_name} -- Pebble socket does "
                f"not exist or is not responsive"
            )
            event.defer()
            return

    def _mount_orc8r_certs(self) -> None:
        """Patch the StatefulSet to include Orchestrator certs secret mount."""
        self.unit.status = MaintenanceStatus(
            "Mounting additional volumes required by the magma-orc8r-bootstrapper container..."
        )
        client = Client()
        try:
            stateful_set = client.get(StatefulSet, name=self.app.name, namespace=self._namespace)
            stateful_set.spec.template.spec.volumes.extend(self._bootstrapper_volumes)  # type: ignore[attr-defined]  # noqa: E501
            stateful_set.spec.template.spec.containers[1].volumeMounts.extend(  # type: ignore[attr-defined]  # noqa: E501
                self._bootstrapper_volume_mounts
            )
            client.patch(
                StatefulSet, name=self.app.name, obj=stateful_set, namespace=self._namespace
            )
        except ApiError as e:
            logger.debug(
                "Failed to mount additional volumes required by the magma-orc8r-bootstrapper "
                "container!"
            )
            raise e
        logger.info("Additional K8s resources for magma-orc8r-bootstrapper container applied!")

    @property
    def _certifier_relation_ready(self) -> bool:
        """Checks whether certifier relation is ready."""
        certifier_relation = self.model.get_relation("certifier")
        if not certifier_relation or len(certifier_relation.units) == 0:
            return False
        if not self._orc8r_certs_mounted:
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
    def _orc8r_certs_mounted(self) -> bool:
        """Check to see if the Orchestrator certs have already been mounted."""
        client = Client()
        statefulset = client.get(StatefulSet, name=self.app.name, namespace=self._namespace)
        return all(
            volume_mount in statefulset.spec.template.spec.containers[1].volumeMounts  # type: ignore[attr-defined]  # noqa: E501
            for volume_mount in self._bootstrapper_volume_mounts
        )

    @property
    def _bootstrapper_volumes(self) -> list:
        """Returns a list of volumes required by the magma-orc8r-bootstrapper container"""
        return [
            Volume(
                name="certs",
                secret=SecretVolumeSource(secretName="orc8r-certs"),
            ),
        ]

    @property
    def _bootstrapper_volume_mounts(self) -> list:
        """Returns a list of volume mounts required by the magma-orc8r-bootstrapper container"""
        return [
            VolumeMount(
                mountPath="/var/opt/magma/certs",
                name="certs",
                readOnly=True,
            ),
        ]

    @property
    def _namespace(self) -> str:
        return self.model.name


if __name__ == "__main__":
    main(MagmaOrc8rBootstrapperCharm)
