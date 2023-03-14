#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Collects runtime metrics from gateways and Orchestrator services."""

import logging
from typing import Union

from charms.observability_libs.v1.kubernetes_service_patch import (
    KubernetesServicePatch,
    ServicePort,
)
from ops.charm import (
    CharmBase,
    PebbleReadyEvent,
    RelationBrokenEvent,
    RelationJoinedEvent,
)
from ops.main import main
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
    ModelError,
    Relation,
    WaitingStatus,
)
from ops.pebble import Layer

logger = logging.getLogger(__name__)


class MagmaOrc8rMetricsdCharm(CharmBase):
    """An instance of this object everytime an event occurs."""

    BASE_CONFIG_PATH = "/var/opt/magma/configs/orc8r"
    REQUIRED_EXTERNAL_RELATIONS = [
        "alertmanager-k8s",
        "alertmanager-configurer-k8s",
        "prometheus-k8s",
        "prometheus-configurer-k8s",
    ]
    REQUIRED_ORC8R_RELATIONS = ["magma-orc8r-orchestrator"]

    def __init__(self, *args):
        """Uses the Orc8rBase library to manage events."""
        super().__init__(*args)
        self._container_name = self._service_name = "magma-orc8r-metricsd"
        self._container = self.unit.get_container(self._container_name)
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[
                ServicePort(name="grpc", port=9180, targetPort=9084),
                ServicePort(name="http", port=8080, targetPort=10084),
                ServicePort(name="grpc-internal", port=9190, targetPort=9184),
            ],
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
        self.framework.observe(
            self.on.magma_orc8r_metricsd_relation_joined,
            self._on_magma_orc8r_metricsd_relation_joined,
        )
        self.framework.observe(
            self.on.magma_orc8r_metricsd_pebble_ready, self._configure_magma_orc8r_metricsd
        )
        for required_rel in self.REQUIRED_EXTERNAL_RELATIONS + self.REQUIRED_ORC8R_RELATIONS:
            self.framework.observe(
                self.on[required_rel].relation_broken, self._on_required_relation_broken
            )

        for required_rel in self.REQUIRED_EXTERNAL_RELATIONS + self.REQUIRED_ORC8R_RELATIONS:
            self.framework.observe(
                self.on[required_rel].relation_joined, self._configure_magma_orc8r_metricsd
            )

    def _configure_magma_orc8r_metricsd(
        self, event: Union[PebbleReadyEvent, RelationJoinedEvent]
    ) -> None:
        """Charm's main callback function, which, after ensuring all conditions are met, handles
        charm setup.

        Args:
            event: Juju PebbleReadyEvent event

        Returns:
            None
        """
        if not self._relations_created:
            event.defer()
            return
        if not self._relations_ready:
            event.defer()
            return
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return
        self._write_config_file()
        self._configure_pebble()

    def _write_config_file(self) -> None:
        """Creates metricsd.yml config file.

        Returns:
            None
        """
        metricsd_config = (
            f'prometheusQueryAddress: "{self._prometheus_url}"\n'
            f'alertmanagerApiURL: "{self._alertmanager_url}/api/v2"\n'
            f'prometheusConfigServiceURL: "{self._prometheus_configurer_url}/v1"\n'
            f'alertmanagerConfigServiceURL: "{self._alertmanager_configurer_url}/v1"\n'
            '"profile": "prometheus"\n'
        )
        self._container.push(f"{self.BASE_CONFIG_PATH}/metricsd.yml", metricsd_config)

    def _configure_pebble(self) -> None:
        """Configures magma-orc8r-metricsd pebble layer.

        Returns:
            None
        """
        self.unit.status = MaintenanceStatus("Configuring pod")
        pebble_layer = self._pebble_layer
        plan = self._container.get_plan()
        if plan.services != pebble_layer.services:
            self._container.add_layer(self._container_name, pebble_layer, combine=True)
            self._container.restart(self._service_name)
            logger.info(f"Restarted container {self._service_name}")
            self._update_relations()
        self.unit.status = ActiveStatus()

    def _update_relations(self) -> None:
        """Updates metricsd service status in relation data bags. This way, charms that
        potentially depend on metricsd can tell whether the service is already running or not.

        Returns:
            None
        """
        if not self.unit.is_leader():
            return
        relations = self.model.relations[self.meta.name]
        for relation in relations:
            self._update_relation_active_status(
                relation=relation, is_active=self._service_is_running
            )

    def _on_magma_orc8r_metricsd_relation_joined(self, event: RelationJoinedEvent) -> None:
        """Sets the status of the metricsd service in the relation data bag. This way, charms that
        potentially depend on metricsd can tell whether the service is already running or not.

        Args:
            event: Juju RelationJoinedEvent event

        Returns:
            None
        """
        if not self.unit.is_leader():
            return
        self._update_relation_active_status(
            relation=event.relation, is_active=self._service_is_running
        )
        if not self._service_is_running:
            event.defer()
            return

    def _on_required_relation_broken(self, event: RelationBrokenEvent):
        """Triggered on relation broken events, sets the status of the charm to blocked.

        Args:
            event(RelationBrokenEvent): juju event
        """
        self.unit.status = BlockedStatus(
            f"Waiting for relation(s) to be created: {event.relation.name}"
        )

    @property
    def _pebble_layer(self) -> Layer:
        """Returns pebble layer with workload service.

        Returns:
            Layer: Pebble Layer
        """
        return Layer(
            {
                "summary": f"{self._service_name} layer",
                "description": f"pebble config layer for {self._service_name}",
                "services": {
                    self._service_name: {
                        "override": "replace",
                        "summary": self._service_name,
                        "startup": "enabled",
                        "command": "metricsd -run_echo_server=true -logtostderr=true -v=0",
                        "environment": self._environment_variables,
                    }
                },
            }
        )

    @property
    def _environment_variables(self) -> dict:
        """Returns the set of environment variables required by the magma-orc8r-metricsd service.

        Returns:
            dict: Environment variables required by the magma-orc8r-metricsd service
        """
        return {
            "SERVICE_HOSTNAME": self._container_name,
            "SERVICE_REGISTRY_MODE": "k8s",
            "SERVICE_REGISTRY_NAMESPACE": self._namespace,
        }

    @property
    def _prometheus_url(self) -> str:
        """Returns the URL of the Prometheus server.

        Returns:
            str: Prometheus URL
        """
        prometheus_service_name = self.model.get_relation("prometheus-k8s").app.name  # type: ignore[union-attr]  # noqa: E501
        # TODO: Get port from the relation data once such information is available.
        return f"http://{prometheus_service_name}:9090"

    @property
    def _prometheus_configurer_url(self) -> str:
        """Returns the URL of the Prometheus Configurer API.

        Returns:
            str: Prometheus Configurer URL
        """
        prometheus_configurer_relation = self.model.get_relation("prometheus-configurer-k8s")
        prometheus_configurer_app = prometheus_configurer_relation.app  # type: ignore[union-attr]
        prometheus_configurer_service_name = prometheus_configurer_relation.data[  # type: ignore[union-attr]  # noqa: E501
            prometheus_configurer_app  # type: ignore[index]
        ][
            "service_name"
        ]
        prometheus_configurer_port = prometheus_configurer_relation.data[  # type: ignore[union-attr]  # noqa: E501
            prometheus_configurer_app  # type: ignore[index]
        ][
            "port"
        ]
        return f"http://{prometheus_configurer_service_name}:{prometheus_configurer_port}"

    @property
    def _alertmanager_url(self) -> str:
        """Returns the URL of the Alertmanager.

        Returns:
            str: Alertmanager URL
        """
        alertmanager_service_name = self.model.get_relation("alertmanager-k8s").app.name  # type: ignore[union-attr]  # noqa: E501
        # TODO: Get port from the relation data once such information is available.
        return f"http://{alertmanager_service_name}:9093"

    @property
    def _alertmanager_configurer_url(self) -> str:
        """Returns the URL of the Alertmanager Configurer API.

        Returns:
            str: Alertmanager Configurer URL
        """
        alertmanager_configurer_relation = self.model.get_relation("alertmanager-configurer-k8s")
        alertmanager_configurer_app = alertmanager_configurer_relation.app  # type: ignore[union-attr]  # noqa: E501
        alertmanager_configurer_service_name = alertmanager_configurer_relation.data[  # type: ignore[union-attr]  # noqa: E501
            alertmanager_configurer_app  # type: ignore[index]
        ][
            "service_name"
        ]
        alertmanager_configurer_port = alertmanager_configurer_relation.data[  # type: ignore[union-attr]  # noqa: E501
            alertmanager_configurer_app  # type: ignore[index]
        ][
            "port"
        ]
        return f"http://{alertmanager_configurer_service_name}:{alertmanager_configurer_port}"

    @property
    def _relations_created(self) -> bool:
        """Checks whether required relations are created.

        Returns:
            bool: True/False
        """
        if missing_relations := [
            relation
            for relation in self.REQUIRED_EXTERNAL_RELATIONS + self.REQUIRED_ORC8R_RELATIONS
            if not self.model.get_relation(relation)
        ]:
            msg = f"Waiting for relation(s) to be created: {', '.join(missing_relations)}"
            self.unit.status = BlockedStatus(msg)
            return False
        return True

    @property
    def _relations_ready(self) -> bool:
        """Checks whether required relations are ready.

        Returns:
            bool: True/False
        """
        if missing_relations := [
            relation
            for relation in self.REQUIRED_ORC8R_RELATIONS
            if not self._relation_active(relation)
        ]:
            msg = f"Waiting for relation(s) to be ready: {', '.join(missing_relations)}"
            self.unit.status = WaitingStatus(msg)
            return False
        return True

    def _relation_active(self, relation_name: str) -> bool:
        """Checks whether related service is ready, by checking its active status provided in the
        relation data bag.

        Args:
            relation_name: The name of the relation

        Returns:
            bool: True/False
        """
        try:
            rel = self.model.get_relation(relation_name)
            units = rel.units  # type: ignore[union-attr]
            return rel.data[next(iter(units))]["active"] == "True"  # type: ignore[union-attr]
        except (AttributeError, KeyError, StopIteration):
            return False

    @property
    def _service_is_running(self) -> bool:
        """Checks whether the workload service is running.

        Returns:
            bool: True/False
        """
        if self._container.can_connect():
            try:
                self._container.get_service(self._service_name)
                return True
            except ModelError:
                pass
        return False

    def _update_relation_active_status(self, relation: Relation, is_active: bool) -> None:
        """Updates service status in the relation data bag.

        Args:
            relation: Juju Relation object to update
            is_active: Workload service status

        Returns:
            None
        """
        relation.data[self.unit].update(
            {
                "active": str(is_active),
            }
        )

    @property
    def _namespace(self) -> str:
        """Returns the namespace pod created by this charm belongs to.

        Returns:
            str: K8s namespace
        """
        return self.model.name


if __name__ == "__main__":
    main(MagmaOrc8rMetricsdCharm)
