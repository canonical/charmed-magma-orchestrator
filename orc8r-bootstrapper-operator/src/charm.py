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
from charms.magma_orc8r_certifier.v0.cert_root_ca import CertRootCARequires
from charms.magma_orc8r_certifier.v0.cert_root_ca import (
    CertificateAvailableEvent as RootCACertificateAvailableEvent,
)
import ops.lib
from ops.charm import CharmBase, InstallEvent, PebbleReadyEvent, RelationJoinedEvent
from ops.main import main
from ops.model import ActiveStatus, ModelError, Relation, WaitingStatus, BlockedStatus
from ops.pebble import Layer
from pgconnstr import ConnectionString  # type: ignore[import]

from private_key import generate_private_key

logger = logging.getLogger(__name__)

pgsql = ops.lib.use("pgsql", 1, "postgresql-charmers@lists.launchpad.net")


class MagmaOrc8rBootstrapperCharm(CharmBase):
    """Main class that is instantiated everytime an event occurs."""

    DB_NAME = "magma_dev"
    BASE_CERTS_PATH = "/var/opt/magma/certs"

    def __init__(self, *args):
        """Initializes all event that need to be observed."""
        super().__init__(*args)
        self._container_name = self._service_name = "magma-orc8r-bootstrapper"
        self._container = self.unit.get_container(self._container_name)
        self._cert_root_ca = CertRootCARequires(self, "cert-root-ca")
        self._db = pgsql.PostgreSQLClient(self, "db")
        self.framework.observe(
            self._db.on.database_relation_joined,
            self._on_database_relation_joined,
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
                        "command": "/usr/bin/envdir "
                        "/var/opt/magma/envdir "
                        "/var/opt/magma/bin/bootstrapper "
                        "-cak=/var/opt/magma/certs/bootstrapper.key "
                        "-logtostderr=true "
                        "-v=0",
                        "environment": {
                            "ORC8R_DOMAIN_NAME": self._domain_name,
                            "SERVICE_HOSTNAME": "magma-orc8r-bootstrapper",
                            "SERVICE_REGISTRY_MODE": "k8s",
                            "SERVICE_REGISTRY_NAMESPACE": self._namespace,
                            "DATABASE_SOURCE": f"dbname={self.DB_NAME} "
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
    def _bootstrapper_private_key_is_pushed(self) -> bool:
        """Returns whether bootstrapper private key is pushed to workload."""
        if not self._container.can_connect():
            return False
        if not self._container.exists(f"{self.BASE_CERTS_PATH}/bootstrapper.key"):
            logger.info("Bootstrapper private key is not pushed")
            return False
        return True

    @property
    def _rootca_is_stored(self) -> bool:
        """Checks whether rootca is stored in the container."""
        if not self._container.can_connect():
            return False
        return self._container.exists(f"{self.BASE_CERTS_PATH}/rootCA.pem")

    @property
    def _db_relation_established(self) -> bool:
        """
        Validates that database relation is established.
        
        That there is a relation and that credentials have been passed.
        """
        if not self._get_db_connection_string:
            return False
        return True

    @property
    def _get_db_connection_string(self):
        """Returns DB connection string provided by the DB relation."""
        try:
            db_relation = self.model.get_relation("db")
            return ConnectionString(db_relation.data[db_relation.app]["master"])  # type: ignore[union-attr, index]  # noqa: E501
        except (AttributeError, KeyError):
            return

    @property
    def _domain_name(self):
        """Returns domain name provided by the orc8r-certifier relation."""
        try:
            certifier_relation = self.model.get_relation("certifier")
            units = certifier_relation.units  # type: ignore[union-attr]
            return certifier_relation.data[next(iter(units))]["domain"]  # type: ignore[union-attr]
        except (KeyError, StopIteration):
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
        self,
        event: Union[PebbleReadyEvent, RootCACertificateAvailableEvent]
    ) -> None:
        """Triggered when pebble is ready.

        Args:
            event (PebbleReadyEvent, RootCACertificateAvailableEvent): Juju event

        Returns:
            None
        """
        if not self._bootstrapper_private_key_is_stored:
            self.unit.status = WaitingStatus("Waiting for bootstrapper private key to be stored")
            event.defer()
            return
        if not self._rootca_is_stored:
            self.unit.status = WaitingStatus("Waiting for rootca to be available.")
            event.defer()
            return
        if not self._bootstrapper_private_key_is_pushed:
            self.unit.status = WaitingStatus("Waiting for bootstrapper private key to be pushed")
            event.defer()
            return
        if not self._db_relation_established:
            self.unit.status = BlockedStatus("Waiting for database relation to be established")
            event.defer()
            return
        self._configure_pebble(event)

    def _configure_pebble(self, event: PebbleReadyEvent) -> None:
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

    def _on_database_relation_joined(self, event):
        """
        Event handler for database relation change.

        - Sets the event.database field on the database joined event.
        - Required because setting the database name is only possible
          from inside the event handler per https://github.com/canonical/ops-lib-pgsql/issues/2
        - Sets our database parameters based on what was provided
          in the relation event.
        """
        if self.unit.is_leader():
            event.database = self.DB_NAME

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
