#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import base64
import logging
from typing import List

from charms.magma_orc8r_libs.v0.orc8r_base import Orc8rBase
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from lightkube import Client
from lightkube.core.exceptions import ApiError
from lightkube.models.core_v1 import SecretVolumeSource, Volume, VolumeMount
from lightkube.models.meta_v1 import ObjectMeta
from lightkube.resources.apps_v1 import StatefulSet
from lightkube.resources.core_v1 import Secret
from ops.charm import CharmBase
from ops.main import main
from ops.model import MaintenanceStatus, WaitingStatus

logger = logging.getLogger(__name__)


class MagmaOrc8rMetricsdCharm(CharmBase):

    METRICSD_SECRET_NAME = "metricsd-config"
    METRICSD_VOLUME_NAME = "metricsd-config-volume"

    def __init__(self, *args):
        """
        An instance of this object everytime an event occurs
        """
        super().__init__(*args)
        self._container_name = self._service_name = "magma-orc8r-metricsd"
        self._container = self.unit.get_container(self._container_name)
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[("grpc", 9180, 9084), ("http", 8080, 10084)],
            additional_labels={
                "app.kubernetes.io/part-of": "orc8r-app",
                "orc8r.io/obsidian_handlers": "true",
                "orc8r.io/swagger_spec": "true",
            },
            additional_annotations={
                "orc8r.io/obsidian_handlers_path_prefixes": "/magma/v1/networks/:network_id/alerts, "  # noqa: E501
                "/magma/v1/networks/:network_id/metrics, "
                "/magma/v1/networks/:network_id/prometheus, "
                "/magma/v1/tenants/:tenant_id/metrics, "
                "/magma/v1/tenants/targets_metadata,"
            },
        )
        startup_command = (
            "/usr/bin/envdir "
            "/var/opt/magma/envdir "
            "/var/opt/magma/bin/metricsd "
            "-run_echo_server=true "
            "-logtostderr=true "
            "-v=0"
        )
        self._orc8r_base = Orc8rBase(self, startup_command=startup_command)
        self.framework.observe(self.on.install, self._on_install)

    def _on_install(self, event):
        if self._container.can_connect():
            self._create_secret()
            self._mount_metricsd_volume()
        else:
            self.unit.status = WaitingStatus("Waiting for container to be ready...")
            event.defer()
            return

    def _create_secret(self):
        self.unit.status = MaintenanceStatus("Creating metricsd secret")
        client = Client()
        secret_data = {
            "metricsd.yml": self._encode_in_base64(open("src/metricsd.yml", "rb").read())
        }
        metadata = ObjectMeta(
            namespace=self._namespace,
            name=self.METRICSD_SECRET_NAME,
        )
        secret = Secret(metadata=metadata, data=secret_data)
        try:
            client.create(secret)
        except ApiError as e:
            logger.info("Failed to create Secret: %s.", str(secret.to_dict()))
            raise e

    @property
    def _metricsd_volumes(self) -> List[Volume]:
        """Returns a list of volumes required by metricsd"""
        return [
            Volume(
                name=self.METRICSD_VOLUME_NAME,
                secret=SecretVolumeSource(secretName=self.METRICSD_SECRET_NAME),
            )
        ]

    @property
    def _metricsd_volume_mounts(self) -> List[VolumeMount]:
        """Returns a list of volume mounts required by metricsd"""
        return [
            VolumeMount(
                mountPath="/var/opt/magma/configs/orc8r",
                name=self.METRICSD_VOLUME_NAME,
            )
        ]

    def _mount_metricsd_volume(self) -> None:
        """Patch the StatefulSet to include volume mounts"""
        self.unit.status = MaintenanceStatus("Mounting additional volumes required by metricsd...")
        client = Client()
        try:
            stateful_set = client.get(StatefulSet, name=self.app.name, namespace=self._namespace)
            stateful_set.spec.template.spec.volumes.extend(self._metricsd_volumes)  # type: ignore[attr-defined]  # noqa: E501
            stateful_set.spec.template.spec.containers[1].volumeMounts.extend(  # type: ignore[attr-defined]  # noqa: E501
                self._metricsd_volume_mounts
            )
            client.patch(
                StatefulSet, name=self.app.name, obj=stateful_set, namespace=self._namespace
            )
        except ApiError as e:
            logger.debug("Failed to mount additional volumes required by metricsd")
            raise e
        logger.info("Additional K8s resources for magma-nms-nginx-proxy container applied!")

    @staticmethod
    def _encode_in_base64(byte_string: bytes):
        """Encodes given byte string in Base64"""
        return base64.b64encode(byte_string).decode("utf-8")

    @property
    def _namespace(self) -> str:
        return self.model.name


if __name__ == "__main__":
    main(MagmaOrc8rMetricsdCharm)
