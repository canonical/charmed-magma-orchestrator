#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
import logging

from charms.magma_orc8r_libs.v0.orc8r_base import Orc8rBase
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from httpx import HTTPStatusError
from lightkube import Client
from lightkube.models.core_v1 import ServicePort, ServiceSpec
from lightkube.models.meta_v1 import ObjectMeta
from lightkube.resources.core_v1 import Service
from ops.charm import CharmBase
from ops.main import main

logger = logging.getLogger(__name__)


class MagmaOrc8rFEGRelayCharm(CharmBase):
    def __init__(self, *args):
        """
        An instance of this object everytime an event occurs.
        """
        super().__init__(*args)
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[("grpc", 9180), ("http", 8080)],
            additional_labels={
                "app.kubernetes.io/part-of": "orc8r-app",
                "orc8r.io/obsidian_handlers": "true",
                "orc8r.io/swagger_spec": "true",
            },
        )
        startup_command = (
            "/usr/bin/envdir "
            "/var/opt/magma/envdir "
            "/var/opt/magma/bin/feg_relay "
            "-logtostderr=true "
            "-v=0"
        )
        self._orc8r_base = Orc8rBase(self, startup_command=startup_command)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.remove, self._on_remove)

    def _on_install(self, event):
        """Handler triggered on install event."""
        self._create_feg_hello_service()

    def _create_feg_hello_service(self) -> None:
        """Creates feg-hello kubernetes service."""
        logger.info("Creating feg-hello kubernetes service")
        client = Client()
        service = self._feg_hello_service()
        if self._service_created(service.metadata.name):
            logger.info("Service already created - Doing nothing.")
        else:
            client.create(obj=service)

    def _feg_hello_service(self) -> Service:
        """Returns feg-hello kubernetes service object."""
        return Service(
            apiVersion="v1",
            kind="Service",
            metadata=ObjectMeta(
                namespace=self._namespace,
                name="orc8r-feg-hello",
                labels={
                    "app.kubernetes.io/component": "feg-orc8r",
                    "app.kubernetes.io/part-of": "orc8r-app",
                },
            ),
            spec=ServiceSpec(
                selector={
                    "app.kubernetes.io/component": "feg-relay",
                },
                ports=[
                    ServicePort(
                        name="grpc",
                        port=9180,
                    ),
                ],
                type="ClusterIP",
            ),
        )

    def _delete_feg_hello_service(self):
        """Deletes feg-hello service from kubernetes."""
        client = Client()
        service = self._feg_hello_service()
        client.delete(Service, name=service.metadata.name, namespace=self._namespace)

    def _service_created(self, service_name: str) -> bool:
        """Checks if service is already created in kubernetes."""
        client = Client()
        try:
            client.get(Service, name=service_name, namespace=self._namespace)
            return True
        except HTTPStatusError:
            return False

    def _on_remove(self, event):
        """Handler triggered on remove event."""
        self._delete_feg_hello_service()

    @property
    def _namespace(self) -> str:
        """Returns Kubernetes namespace."""
        return self.model.name


if __name__ == "__main__":
    main(MagmaOrc8rFEGRelayCharm)
