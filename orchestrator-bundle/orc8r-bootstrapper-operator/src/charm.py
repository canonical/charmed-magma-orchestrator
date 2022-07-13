#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""magma-orc8r-bootstrapper.

Bootstrapper manages the certificate bootstrapping process for newly registered gateways and
gateways whose cert has expired
"""

import logging
from typing import Union

from charms.magma_orc8r_certifier.v0.cert_bootstrapper import (
    CertBootstrapperRequires,
    PrivateKeyAvailableEvent,
)
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from charms.observability_libs.v1.kubernetes_service_patch import (
    KubernetesServicePatch,
    ServicePort,
)
from ops.charm import (
    CharmBase,
    PebbleReadyEvent,
    RelationChangedEvent,
    RelationJoinedEvent,
)
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, ModelError, Relation, WaitingStatus
from ops.pebble import Layer

logger = logging.getLogger(__name__)


class MagmaOrc8rBootstrapperCharm(CharmBase):
    """Main class that is instantiated everytime an event occurs."""

    CERTIFICATE_DIRECTORY = "/var/opt/magma/certs"

    def __init__(self, *args):
        """Initializes all event that need to be observed."""
        super().__init__(*args)
        self._container_name = self._service_name = "magma-orc8r-bootstrapper"
        self._container = self.unit.get_container(self._container_name)
        self.cert_bootstrapper = CertBootstrapperRequires(
            charm=self, relationship_name="cert-bootstrapper"
        )
        self.framework.observe(
            self.on.magma_orc8r_bootstrapper_pebble_ready,
            self._on_magma_orc8r_bootstrapper_pebble_ready,
        )
        self.framework.observe(
            self.on.magma_orc8r_bootstrapper_relation_joined,
            self._on_magma_orc8r_bootstrapper_relation_joined,
        )
        self.framework.observe(
            self.cert_bootstrapper.on.private_key_available,
            self._on_private_key_available
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
    def _certs_are_stored(self) -> bool:
        """Returns whether the bootstrapper private key is stored.

        Returns:
            bool: True/False
        """
        return self._container.exists(f"{self.CERTIFICATE_DIRECTORY}/bootstrapper.key")

    @property
    def _cert_bootstrapper_relation_created(self) -> bool:
        """Returns whether cert-bootstrapper relation is created.

        Returns:
            bool: True/False
        """
        return self._relation_created("cert-bootstrapper")

    def _relation_created(self, relation_name: str) -> bool:
        """Returns whether given relation was created.

        Args:
            relation_name (str): Relation name

        Returns:
            bool: True/False
        """
        try:
            if self.model.get_relation(relation_name):
                return True
            return False
        except KeyError:
            return False

    def _on_magma_orc8r_bootstrapper_pebble_ready(
        self, event: Union[PebbleReadyEvent, PrivateKeyAvailableEvent]
    ) -> None:
        """Triggered when pebble is ready.

        Args:
            event (PebbleReadyEvent, PrivateKeyAvailableEvent): Juju event

        Returns:
            None
        """
        if not self._cert_bootstrapper_relation_created:
            self.unit.status = BlockedStatus(
                "Waiting for cert-bootstrapper relation to be created"
            )
            event.defer()
            return
        if not self._certs_are_stored:
            self.unit.status = WaitingStatus("Waiting for certs to be available")
            event.defer()
            return
        self._configure_pebble(event)

    def _configure_pebble(self, event: Union[PebbleReadyEvent, PrivateKeyAvailableEvent]) -> None:
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

    def _on_private_key_available(self, event: PrivateKeyAvailableEvent) -> None:
        """Triggered when bootstrapper private key is available from relation data.

        Args:
            event (PrivateKeyAvailableEvent): Event for whenever private key is available.

        Returns:
            None
        """
        logger.info("Bootstrapper private key available")
        if not self._container.can_connect():
            logger.info("Can't connect to container - Deferring")
            event.defer()
            return
        self._container.push(
            path=f"{self.CERTIFICATE_DIRECTORY}/bootstrapper.key", source=event.private_key
        )
        self._on_magma_orc8r_bootstrapper_pebble_ready(event)


if __name__ == "__main__":
    main(MagmaOrc8rBootstrapperCharm)
