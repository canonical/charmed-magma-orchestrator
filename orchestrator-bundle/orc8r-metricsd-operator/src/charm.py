#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer

logger = logging.getLogger(__name__)


class MagmaOrc8rMetricsdCharm(CharmBase):

    BASE_CONFIG_PATH = "/var/opt/magma/configs/orc8r"

    # TODO: The various URL's should be provided through relationships.
    PROMETHEUS_URL = "http://orc8r-prometheus:9090"
    PROMETHEUS_CONFIGURER_URL = "http://orc8r-prometheus:9100"
    ALERTMANAGER_URL = "http://orc8r-alertmanager:9093"
    ALERTMANAGER_CONFIGURER_URL = "http://orc8r-alertmanager:9101"

    def __init__(self, *args):
        """
        An instance of this object everytime an event occurs.
        """
        super().__init__(*args)
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
        self._container_name = self._service_name = "magma-orc8r-metricsd"
        self._container = self.unit.get_container(self._container_name)
        self.framework.observe(self.on.magma_orc8r_metricsd_pebble_ready, self._on_pebble_ready)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(
            self.on.magma_service_registry_relation_joined, self._on_relation_joined
        )
        self.framework.observe(
            self.on.magma_service_registry_relation_broken, self._on_relation_broken
        )

    def _on_install(self, event):
        self._write_config_file()

    def _on_relation_joined(self, event):
        self._configure_orc8r(event)

    def _on_pebble_ready(self, event):
        if not self._service_registry_relation_created:
            self.unit.status = BlockedStatus("Waiting for service registry relation to be created")
            event.defer()
            return
        self._configure_orc8r(event)

    def _on_relation_broken(self, event):
        logger.info("Relation with service-registry broken - Stopping service")
        self._container.stop(self._service_name)
        self.unit.status = BlockedStatus("Waiting for service registry relation to be created")

    def _write_config_file(self):
        self.unit.status = MaintenanceStatus("Writing config file metricsd.yml")
        metricsd_config = (
            f'prometheusQueryAddress: "{self.PROMETHEUS_URL}"\n'
            f'alertmanagerApiURL: "{self.ALERTMANAGER_URL}/api/v2"\n'
            f'prometheusConfigServiceURL: "{self.PROMETHEUS_CONFIGURER_URL}/v1"\n'
            f'alertmanagerConfigServiceURL: "{self.ALERTMANAGER_CONFIGURER_URL}/v1"\n'
            '"profile": "prometheus"\n'
        )
        self._container.push(f"{self.BASE_CONFIG_PATH}/metricsd.yml", metricsd_config)

    def _configure_orc8r(self, event):
        """
        Adds layer to pebble config if the proposed config is different from the current one
        """
        if self._container.can_connect():
            self.unit.status = MaintenanceStatus("Configuring pod")
            pebble_layer = self._pebble_layer()
            plan = self._container.get_plan()
            if plan.services != pebble_layer.services:
                self._container.add_layer(self._container_name, pebble_layer, combine=True)
            self._container.restart(self._service_name)
            logger.info(f"Restarted container {self._service_name}")
            self.unit.status = ActiveStatus()
        else:
            self.unit.status = WaitingStatus("Waiting for container to be ready...")
            event.defer()

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
                        "command": (
                            "/usr/bin/envdir "
                            "/var/opt/magma/envdir "
                            "/var/opt/magma/bin/metricsd "
                            "-run_echo_server=true "
                            "-logtostderr=true "
                            "-v=0"
                        ),
                        "environment": self._environment_variables,
                    }
                },
            }
        )

    @property
    def _environment_variables(self):
        return {
            "SERVICE_HOSTNAME": self._container_name,
            "SERVICE_REGISTRY_MODE": "k8s",
            "SERVICE_REGISTRY_NAMESPACE": self._namespace,
        }

    @property
    def _namespace(self) -> str:
        return self.model.name

    @property
    def _service_registry_relation_created(self) -> bool:
        """Checks whether charm is related to magma-service-registry."""
        aa = self.model.get_relation("magma-service-registry")
        logger.info(aa)
        if not self.model.get_relation("magma-service-registry"):
            return False
        return True


if __name__ == "__main__":
    main(MagmaOrc8rMetricsdCharm)
