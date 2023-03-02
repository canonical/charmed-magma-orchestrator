#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Acts like an intermediary for different magma services."""

import logging
import re
from typing import Tuple, Union

from charms.observability_libs.v1.kubernetes_service_patch import (
    KubernetesServicePatch,
    ServicePort,
)
from ops.charm import (
    CharmBase,
    ConfigChangedEvent,
    InstallEvent,
    PebbleReadyEvent,
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


class MagmaOrc8rEventdCharm(CharmBase):
    """An instance of this object everytime an event occurs."""

    BASE_CONFIG_PATH = "/var/opt/magma/configs/orc8r"

    def __init__(self, *args):
        """Uses the Orc8rBase library to manage events."""
        super().__init__(*args)
        self._container_name = self._service_name = "magma-orc8r-eventd"
        self._container = self.unit.get_container(self._container_name)
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[
                ServicePort(name="grpc", port=9180, targetPort=9121),
                ServicePort(name="http", port=8080, targetPort=10121),
            ],
            additional_labels={
                "app.kubernetes.io/part-of": "orc8r-app",
                "orc8r.io/obsidian_handlers": "true",
                "orc8r.io/swagger_spec": "true",
            },
            additional_annotations={
                "orc8r.io/obsidian_handlers_path_prefixes": "/magma/v1/networks/:network_id/logs, "
                "/magma/v1/events,"
            },
        )

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(
            self.on.magma_orc8r_eventd_pebble_ready, self._configure_magma_orc8r_eventd
        )
        self.framework.observe(self.on.config_changed, self._configure_magma_orc8r_eventd)

        self.framework.observe(
            self.on.magma_orc8r_eventd_relation_joined,
            self._on_magma_orc8r_eventd_relation_joined,
        )

    def _on_install(self, event: InstallEvent) -> None:
        """Triggered on charm installation.

        Writes elasticsearch config file to the workload container.

        Args:
            event: Juju event (InstallEvent)
        """
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return
        if not self._elasticsearch_config_is_valid:
            self.unit.status = BlockedStatus(
                "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
            )
            return
        self._push_config_file_to_workload()

    def _configure_magma_orc8r_eventd(
        self, event: Union[ConfigChangedEvent, PebbleReadyEvent]
    ) -> None:
        """Charm's main callback function.

        After ensuring all conditions are met, handles charm setup.

        Args:
            event: Juju events (ConfigChangedEvent or PebbleReadyEvent)
        """
        if not self._elasticsearch_config_is_valid:
            self.unit.status = BlockedStatus(
                "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
            )
            return
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return
        self._push_config_file_to_workload()
        self._configure_pebble()

    def _on_magma_orc8r_eventd_relation_joined(self, event: RelationJoinedEvent) -> None:
        """Sets the status of the eventd service in the relation data bag.

        This way, charms that potentially depend on eventd can tell whether the service
        is already running or not.

        Args:
            event: Juju RelationJoinedEvent event
        """
        if not self.unit.is_leader():
            return
        self._update_relation_active_status(
            relation=event.relation, is_active=self._service_is_running
        )
        if not self._service_is_running:
            event.defer()
            return

    def _push_config_file_to_workload(self) -> None:
        """Writes elasticsearch config file to the workload container."""
        elasticsearch_url, elasticsearch_port = self._get_elasticsearch_config()
        elastic_config = (
            f'"elasticHost": "{elasticsearch_url}"\n' f'"elasticPort": {elasticsearch_port}\n'
        )
        self._container.push(f"{self.BASE_CONFIG_PATH}/elastic.yml", elastic_config)
        logger.info(f"Config file pushed to {self.BASE_CONFIG_PATH}/elastic.yml")

    def _get_elasticsearch_config(self) -> Tuple[str, str]:
        """Splits elasticsearch-url config param into host address and port.

        Returns:
            Tuple[str, str]: (elasticsearch_host, elasticsearch_port)
        """
        # TODO: Elasticsearch url should be passed through a relationship (not a config)
        elasticsearch_url = self.model.config.get("elasticsearch-url")
        elasticsearch_url_split = elasticsearch_url.split(":")  # type: ignore[union-attr]
        return elasticsearch_url_split[0], elasticsearch_url_split[1]

    @property
    def _elasticsearch_config_is_valid(self) -> bool:
        """Checks whether the elasticsearch-url config param is valid.

        Returns:
            bool: Whether the elasticsearch-url config param is valid
        """
        elasticsearch_url = self.model.config.get("elasticsearch-url")
        if not elasticsearch_url:
            return False
        if re.match("^[a-zA-Z0-9._-]+:[0-9]+$", elasticsearch_url):
            return True
        else:
            return False

    def _configure_pebble(self) -> None:
        """Configures magma-orc8r-eventd pebble layer."""
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
        """Updates eventd service status in relation data bags.

        This way, charms that potentially depend on eventd can tell whether the service
        is already running or not.
        """
        if not self.unit.is_leader():
            return
        relations = self.model.relations[self.meta.name]
        for relation in relations:
            self._update_relation_active_status(
                relation=relation, is_active=self._service_is_running
            )

    def _update_relation_active_status(self, relation: Relation, is_active: bool) -> None:
        """Updates service status in the relation data bag.

        Args:
            relation: Juju Relation object to update
            is_active: Workload service status
        """
        relation.data[self.unit].update(
            {
                "active": str(is_active),
            }
        )

    @property
    def _service_is_running(self) -> bool:
        """Checks whether the workload service is running.

        Returns:
            bool: Whether the workload service is running
        """
        if self._container.can_connect():
            try:
                self._container.get_service(self._service_name)
                return True
            except ModelError:
                pass
        return False

    @property
    def _pebble_layer(self) -> Layer:
        """Returns pebble layer for the charm.

        Returns:
            Layer: Pebble layer
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
                        "command": "eventd -run_echo_server=true -logtostderr=true -v=0",
                        "environment": self._environment_variables,
                    }
                },
            }
        )

    @property
    def _environment_variables(self) -> dict:
        """Returns the set of environment variables required by the magma-orc8r-eventd service.

        Returns:
            dict: Environment variables required by the magma-orc8r-eventd service
        """
        return {
            "SERVICE_HOSTNAME": self._container_name,
            "SERVICE_REGISTRY_MODE": "k8s",
            "SERVICE_REGISTRY_NAMESPACE": self._namespace,
        }

    @property
    def _namespace(self) -> str:
        """Returns the namespace pod created by this charm belongs to.

        Returns:
            str: K8s namespace
        """
        return self.model.name


if __name__ == "__main__":
    main(MagmaOrc8rEventdCharm)
