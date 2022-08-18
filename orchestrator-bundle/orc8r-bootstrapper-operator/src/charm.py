#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Manages the certificate bootstrapping process for registered gateways."""

import logging
from typing import Optional, Union

from charms.observability_libs.v1.kubernetes_service_patch import (
    KubernetesServicePatch,
    ServicePort,
)
from ops.charm import CharmBase, InstallEvent, PebbleReadyEvent, RelationJoinedEvent
from ops.main import main
from ops.model import ActiveStatus, ModelError, Relation, WaitingStatus
from ops.pebble import Layer

from private_key import generate_private_key

logger = logging.getLogger(__name__)


class MagmaOrc8rBootstrapperCharm(CharmBase):
    """Main class that is instantiated everytime an event occurs."""

    CERTIFICATE_DIRECTORY = "/var/opt/magma/certs"

    def __init__(self, *args):
        """Initializes all event that need to be observed."""
        super().__init__(*args)
        self._container_name = self._service_name = "magma-orc8r-bootstrapper"
        self._container = self.unit.get_container(self._container_name)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(
            self.on.magma_orc8r_bootstrapper_pebble_ready,
            self._on_magma_orc8r_bootstrapper_pebble_ready,
        )
        self.framework.observe(
            self.on.magma_orc8r_bootstrapper_relation_joined,
            self._on_magma_orc8r_bootstrapper_relation_joined,
        )
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[ServicePort(name="grpc", port=9180, targetPort=9088)],
            additional_labels={"app.kubernetes.io/part-of": "orc8r-app"},
        )

    @property
    def _pebble_layer(self) -> Layer:
        """Returns pebble layer for the charm.

        Returns:
            Layer: Pebble Layer
        """
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
    def _namespace(self) -> str:
        """Returns the namespace.

        Returns:
            str: Kubernetes namespace.
        """
        return self.model.name

    @property
    def _service_is_running(self) -> bool:
        """Retrieves the workload service and returns whether it is running.

        Returns:
            bool: Whether service is running
        """
        if self._container.can_connect():
            try:
                self._container.get_service(self._service_name)
                return True
            except ModelError:
                pass
        return False

    @property
    def _bootstrapper_private_key(self) -> Optional[str]:
        """Returns bootstrapper private key.

        Returns:
            str: Private key
        """
        replicas = self.model.get_relation("replicas")
        if not replicas:
            return None
        return replicas.data[self.app].get("bootstrapper_private_key", None)

    @property
    def _bootstrapper_private_key_is_stored(self) -> bool:
        """Returns whether certificates are stored in relation data.

        Returns:
            bool: Whether certificates have been generated.
        """
        if not self._bootstrapper_private_key:
            logger.info("Bootstrapper private key not stored")
            return False
        return True

    @property
    def _replicas_relation_created(self) -> bool:
        """Returns whether the replicas Juju relation was crated.

        Returns:
            str: Whether the relation was created.
        """
        if not self.model.get_relation("replicas"):
            return False
        return True

    @property
    def _bootstrapper_private_key_is_pushed(self) -> bool:
        """Returns whether bootstrapper private key is pushed to workload.

        Returns:
            bool: Whether bootstrapper private key is pushed to workload.
        """
        if not self._container.exists(f"{self.CERTIFICATE_DIRECTORY}/bootstrapper.key"):
            logger.info("Bootstrapper private key is not pushed")
            return False
        return True

    def _on_install(self, event: InstallEvent) -> None:
        """Triggered on charm install.

        Args:
            event: Juju event

        Returns:
            None
        """
        if not self._replicas_relation_created:
            self.unit.status = WaitingStatus("Waiting for replicas relation to be created")
            event.defer()
            return
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return
        if self.unit.is_leader():
            bootstrapper_key = generate_private_key()
            self._store_bootstrapper_private_key(bootstrapper_key.decode())
        elif not self._bootstrapper_private_key_is_stored:
            self.unit.status = WaitingStatus(
                "Waiting for leader to generate bootstrapper private key"
            )
            event.defer()
            return
        self._push_bootstrapper_private_key()

    def _push_bootstrapper_private_key(self) -> None:
        """Pushes bootstrapper private key to workload container."""
        if not self._bootstrapper_private_key:
            raise RuntimeError("Bootstrapper private key is not available")
        self._container.push(
            path=f"{self.CERTIFICATE_DIRECTORY}/bootstrapper.key",
            source=self._bootstrapper_private_key,
        )

    def _store_bootstrapper_private_key(self, private_key: str) -> None:
        """Stores bootstrapper private key in peer relation data."""
        peer_relation = self.model.get_relation("replicas")
        if not peer_relation:
            raise RuntimeError("No peer relation")
        peer_relation.data[self.app].update({"bootstrapper_private_key": private_key})

    def _on_magma_orc8r_bootstrapper_pebble_ready(self, event: Union[PebbleReadyEvent]) -> None:
        """Triggered when pebble is ready.

        Args:
            event (PebbleReadyEvent, PrivateKeyAvailableEvent): Juju event

        Returns:
            None
        """
        if not self._bootstrapper_private_key_is_stored:
            self.unit.status = WaitingStatus("Waiting for bootstrapper private key to be stored")
            event.defer()
            return
        if not self._bootstrapper_private_key_is_pushed:
            self.unit.status = WaitingStatus("Waiting for bootstrapper private key to be pushed")
            event.defer()
            return
        self._configure_pebble(event)

    def _configure_pebble(self, event: Union[PebbleReadyEvent]) -> None:
        """Adds layer to pebble config if the proposed config is different from the current one."""
        if self._container.can_connect():
            pebble_layer = self._pebble_layer
            plan = self._container.get_plan()
            if plan.services != pebble_layer.services:
                self._container.add_layer(self._container_name, pebble_layer, combine=True)
                self._container.restart(self._service_name)
                logger.info(f"Restarted container {self._service_name}")
                self._update_relations()
                self.unit.status = ActiveStatus()
        else:
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()

    def _on_magma_orc8r_bootstrapper_relation_joined(self, event: RelationJoinedEvent) -> None:
        """Triggered when requirers join the bootstrapper relation.

        Args:
            event (RelationJoinedEvent): Juju event

        Returns:
            None
        """
        self._update_relations()
        if not self._service_is_running:
            event.defer()
            return

    def _update_relation_active_status(self, relation: Relation, is_active: bool) -> None:
        """Updates the relation data with the active status.

        Args:
            relation (Relation): Juju relation
            is_active (bool): Whether workload service is active.

        Returns:
            None
        """
        relation.data[self.unit].update(
            {
                "active": str(is_active),
            }
        )

    def _update_relations(self) -> None:
        """Updates relations with the workload service status.

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


if __name__ == "__main__":
    main(MagmaOrc8rBootstrapperCharm)
