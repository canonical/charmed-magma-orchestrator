#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus
from ops.pebble import ConnectionError, Layer

logger = logging.getLogger(__name__)


class MagmaOrc8rMetricsdCharm(CharmBase):
    """Charm the service."""

    def __init__(self, *args):
        """
        An instance of this object everytime an event occurs
        """
        super().__init__(*args)
        self._container_name = self._service_name = "magma-orc8r-metricsd"
        self._container = self.unit.get_container(self._container_name)
        self.framework.observe(
            self.on.magma_orc8r_metricsd_pebble_ready, self._on_magma_orc8r_metricsd_pebble_ready
        )
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

    def _on_magma_orc8r_metricsd_pebble_ready(self, event):
        """
        Triggered when pebble is ready
        """
        self._configure_orc8r(event)

    def _pebble_layer(self) -> Layer:
        """Returns pebble layer for the charm."""
        return Layer(
            {
                "summary": f"{self._service_name} layer",
                "description": f"pebble config layer for {self._service_name}",
                "services": {
                    self._service_name: {
                        "override": "replace",
                        "summary": self._service_name,
                        "startup": "enabled",
                        "command": "/usr/bin/envdir "
                        "/var/opt/magma/envdir "
                        "/var/opt/magma/bin/metricsd "
                        "-run_echo_server=true "
                        "-logtostderr=true "
                        "-v=0",
                        "environment": {
                            "SERVICE_HOSTNAME": self._service_name,
                            "SERVICE_REGISTRY_MODE": "k8s",
                            "SERVICE_REGISTRY_NAMESPACE": self._namespace,
                        },
                    }
                },
            }
        )

    def _configure_orc8r(self, event):
        """
        Adds layer to pebble config if the proposed config is different from the current one
        """
        pebble_layer = self._pebble_layer()
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

    @property
    def _namespace(self) -> str:
        return self.model.name


if __name__ == "__main__":
    main(MagmaOrc8rMetricsdCharm)
