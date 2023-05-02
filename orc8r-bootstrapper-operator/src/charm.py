#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Manages the certificate bootstrapping process for registered gateways."""

import logging
from typing import Optional, Union

import psycopg2  # type: ignore[import]
from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires
from charms.magma_orc8r_certifier.v0.cert_root_ca import (
    CertificateAvailableEvent as RootCACertificateAvailableEvent,
)
from charms.magma_orc8r_certifier.v0.cert_root_ca import CertRootCARequires
from charms.observability_libs.v1.kubernetes_service_patch import (
    KubernetesServicePatch,
    ServicePort,
)
from ops.charm import (
    CharmBase,
    InstallEvent,
    PebbleReadyEvent,
    RelationBrokenEvent,
    RelationJoinedEvent,
)
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, ModelError, Relation, WaitingStatus
from ops.pebble import Layer
from pgconnstr import ConnectionString  # type: ignore[import]

from private_key import generate_private_key

logger = logging.getLogger(__name__)


class MagmaOrc8rBootstrapperCharm(CharmBase):
    """Main class that is instantiated every time an event occurs."""

    DB_NAME = "magma_dev"
    BASE_CERTS_PATH = "/var/opt/magma/certs"
    CERT_ROOT_CA_RELATION = "cert-root-ca"

    def __init__(self, *args):
        """Initializes all event that need to be observed."""
        super().__init__(*args)
        self._container_name = self._service_name = "magma-orc8r-bootstrapper"
        self._container = self.unit.get_container(self._container_name)
        self._cert_root_ca = CertRootCARequires(self, self.CERT_ROOT_CA_RELATION)
        self._database = DatabaseRequires(
            self, relation_name="database", database_name=self.DB_NAME
        )
        self.framework.observe(self.on.database_relation_broken, self._on_database_relation_broken)
        self.framework.observe(
            self._database.on.database_created,
            self._configure_magma_orc8r_bootstrapper,
        )
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(
            self.on.magma_orc8r_bootstrapper_pebble_ready,
            self._configure_magma_orc8r_bootstrapper,
        )
        self.framework.observe(
            self.on.magma_orc8r_bootstrapper_relation_joined,
            self._on_magma_orc8r_bootstrapper_relation_joined,
        )
        self.framework.observe(
            self._cert_root_ca.on.certificate_available, self._on_root_ca_certificate_available
        )
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[
                ServicePort(name="grpc", port=9180, targetPort=9088),
                ServicePort(name="grpc-internal", port=9190, targetPort=9188),
            ],
            additional_labels={"app.kubernetes.io/part-of": "orc8r-app"},
        )

    @property
    def _pebble_layer(self) -> Layer:
        """Returns pebble layer for the charm."""
        return Layer(
            {
                "summary": f"{self._service_name} pebble layer",
                "services": {
                    self._service_name: {
                        "override": "replace",
                        "startup": "enabled",
                        "command": "bootstrapper "
                        "-cak=/var/opt/magma/certs/bootstrapper.key "
                        "-logtostderr=true "
                        "-v=0",
                        "environment": {
                            "SERVICE_HOSTNAME": "magma-orc8r-bootstrapper",
                            "SERVICE_REGISTRY_MODE": "k8s",
                            "SERVICE_REGISTRY_NAMESPACE": self._namespace,
                            "DATABASE_SOURCE": f"dbname={self.DB_NAME} "  # type: ignore[union-attr] # noqa: E501
                            f"user={self._get_db_connection_string.user} "
                            f"password={self._get_db_connection_string.password} "
                            f"host={self._get_db_connection_string.host} "
                            f"port={self._get_db_connection_string.port} "
                            f"sslmode=disable",
                            "SQL_DRIVER": "postgres",
                            "SQL_DIALECT": "psql",
                        },
                    }
                },
            }
        )

    @property
    def _namespace(self) -> str:
        """Returns the Kubernetes namespace."""
        return self.model.name

    @property
    def _service_is_running(self) -> bool:
        """Retrieves the workload service and returns whether it is running."""
        if self._container.can_connect():
            try:
                self._container.get_service(self._service_name)
                return True
            except ModelError:
                pass
        return False

    @property
    def _bootstrapper_private_key(self) -> Optional[str]:
        """Returns bootstrapper private key."""
        replicas = self.model.get_relation("replicas")
        if not replicas:
            return None
        return replicas.data[self.app].get("bootstrapper_private_key", None)

    @property
    def _bootstrapper_private_key_is_stored(self) -> bool:
        """Returns whether bootstrapper private key is stored in peer relation data."""
        if not self._bootstrapper_private_key:
            logger.info("Bootstrapper private key not stored")
            return False
        return True

    @property
    def _replicas_relation_created(self) -> bool:
        """Returns whether the replicas Juju relation was created."""
        if not self.model.get_relation("replicas"):
            return False
        return True

    @property
    def _cert_root_ca_relation_created(self) -> bool:
        """Returns whether cert-root-ca relation is created.

        Returns:
            bool: True/False
        """
        return self._relation_created(self.CERT_ROOT_CA_RELATION)

    @property
    def _bootstrapper_private_key_is_pushed(self) -> bool:
        """Returns whether bootstrapper private key is pushed to workload."""
        if not self._container.can_connect():
            return False
        if not self._container.exists(f"{self.BASE_CERTS_PATH}/bootstrapper.key"):
            logger.info("Bootstrapper private key is not pushed")
            return False
        return True

    @property
    def _root_ca_is_pushed(self) -> bool:
        """Checks whether rootca is stored in the container."""
        if not self._container.can_connect():
            return False
        return self._container.exists(f"{self.BASE_CERTS_PATH}/rootCA.pem")

    @property
    def _db_relation_created(self) -> bool:
        """Validates that database relation is created.

        That there is a relation and that credentials have been passed.
        """
        return self._relation_created("database")

    @property
    def _db_relation_established(self) -> bool:
        """Validates that database relation is established.

        Checks that there is a relation and that credentials have been passed.

        Returns:
            bool: Whether the database relation is established.
        """
        db_connection_string = self._get_db_connection_string
        if not db_connection_string:
            return False
        try:
            psycopg2.connect(
                f"dbname='{self.DB_NAME}' "
                f"user='{db_connection_string.user}' "
                f"host='{db_connection_string.host}' "
                f"password='{db_connection_string.password}'"
            ).close()
            return True
        except psycopg2.OperationalError:
            return False

    @property
    def _get_db_connection_string(self) -> Optional[ConnectionString]:
        """Returns DB connection string provided by the DB relation.

        Returns:
            Optional[ConnectionString]: pgconnstr ConnectionString object.
        """
        try:
            relation_data = next(iter(self._database.fetch_relation_data().values()))
            connection_info = {
                "dbname": relation_data["database"],
                "user": relation_data["username"],
                "password": relation_data["password"],
                "host": relation_data["endpoints"].split(":")[0],
                "port": relation_data["endpoints"].split(":")[1].split(",")[0],
            }
            return ConnectionString(**connection_info)
        except (AttributeError, KeyError):
            return None

    def _on_root_ca_certificate_available(self, event: RootCACertificateAvailableEvent) -> None:
        """Triggered when rootCA certificate is available.

        Stores the rootCA certificate in the workload container's storage.

        Args:
            event (RootCACertificateAvailableEvent): Juju event
        """
        logger.info("rootCA certificate available")
        if not self._container.can_connect():
            logger.info("Can't connect to container - Deferring")
            event.defer()
            return
        self._container.push(path=f"{self.BASE_CERTS_PATH}/rootCA.pem", source=event.certificate)
        self._configure_magma_orc8r_bootstrapper(event)

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

    def _on_database_relation_broken(self, event: RelationBrokenEvent):
        """Event handler for database relation broken.

        Args:
            event (RelationBrokenEvent): Juju event
        Returns:
            None
        """
        self.unit.status = BlockedStatus("Waiting for database relation to be created")

    def _push_bootstrapper_private_key(self) -> None:
        """Pushes bootstrapper private key to workload container."""
        if not self._bootstrapper_private_key:
            raise RuntimeError("Bootstrapper private key is not available")
        self._container.push(
            path=f"{self.BASE_CERTS_PATH}/bootstrapper.key",
            source=self._bootstrapper_private_key,
        )

    def _store_bootstrapper_private_key(self, private_key: str) -> None:
        """Stores bootstrapper private key in peer relation data."""
        peer_relation = self.model.get_relation("replicas")
        if not peer_relation:
            raise RuntimeError("No peer relation")
        peer_relation.data[self.app].update({"bootstrapper_private_key": private_key})

    def _configure_magma_orc8r_bootstrapper(
        self, event: Union[PebbleReadyEvent, RootCACertificateAvailableEvent]
    ) -> None:
        """Triggered when pebble is ready.

        Args:
            event (PebbleReadyEvent, RootCACertificateAvailableEvent): Juju event

        Returns:
            None
        """
        if not self._cert_root_ca_relation_created:
            self.unit.status = BlockedStatus(
                f"Waiting for {self.CERT_ROOT_CA_RELATION} relation to be created"
            )
            event.defer()
            return
        if not self._bootstrapper_private_key_is_stored:
            self.unit.status = WaitingStatus("Waiting for bootstrapper private key to be stored")
            event.defer()
            return
        if not self._bootstrapper_private_key_is_pushed:
            self.unit.status = WaitingStatus("Waiting for bootstrapper private key to be pushed")
            event.defer()
            return
        if not self._db_relation_created:
            self.unit.status = BlockedStatus("Waiting for database relation to be created")
            event.defer()
            return
        if not self._db_relation_established:
            self.unit.status = WaitingStatus("Waiting for database relation to be ready")
            event.defer()
            return
        if not self._root_ca_is_pushed:
            self.unit.status = WaitingStatus("Waiting for root ca to be pushed.")
            event.defer()
            return
        self._configure_pebble(event)

    def _configure_pebble(
        self, event: Union[PebbleReadyEvent, RootCACertificateAvailableEvent]
    ) -> None:
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
