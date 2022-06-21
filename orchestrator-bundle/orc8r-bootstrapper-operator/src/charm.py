#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import ops.lib
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from lightkube import Client
from lightkube.core.exceptions import ApiError
from lightkube.models.core_v1 import SecretVolumeSource, Volume, VolumeMount
from lightkube.resources.apps_v1 import StatefulSet
from ops.charm import (
    CharmBase,
    PebbleReadyEvent,
    RelationChangedEvent,
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
from pgconnstr import ConnectionString  # type: ignore[import]

logger = logging.getLogger(__name__)
pgsql = ops.lib.use("pgsql", 1, "postgresql-charmers@lists.launchpad.net")

class MagmaOrc8rBootstrapperCharm(CharmBase):
    
    DB_NAME = "magma_dev"

    def __init__(self, *args):
        super().__init__(*args)
        self._container_name = self._service_name = "magma-orc8r-bootstrapper"
        self._container = self.unit.get_container(self._container_name)
        self._db = pgsql.PostgreSQLClient(self, "db")
        self.framework.observe(
            self.on.magma_orc8r_bootstrapper_pebble_ready,
            self._on_magma_orc8r_bootstrapper_pebble_ready,
        )
        self.framework.observe(
            self.on.magma_orc8r_certifier_relation_changed,
            self._on_magma_orc8r_certifier_relation_changed,
        )
        self.framework.observe(
            self.on.magma_orc8r_bootstrapper_relation_joined,
            self._on_magma_orc8r_bootstrapper_relation_joined,
        )
        self.framework.observe(
            self._db.on.database_relation_joined, self._on_database_relation_joined
        )
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[("grpc", 9180, 9088)],
            additional_labels={"app.kubernetes.io/part-of": "orc8r-app"},
        )

    def _on_magma_orc8r_bootstrapper_pebble_ready(self, event: PebbleReadyEvent):
        """Triggered when pebble is ready."""
        if not self._certifier_relation_created:
            self.unit.status = BlockedStatus(
                "Waiting for magma-orc8r-certifier relation to be created"
            )
            event.defer()
            return
        if not self._certifier_relation_ready:
            self.unit.status = WaitingStatus(
                "Waiting for magma-orc8r-certifier relation to be ready"
            )
            event.defer()
            return
        if not self._orc8r_certs_mounted:
            self.unit.status = WaitingStatus("Waiting for NMS certificates to be mounted")
            event.defer()
            return
        if not self._db_relation_established:
            self.unit.status = BlockedStatus("Waiting for database relation to be established")
            event.defer()
            return
        self._configure_pebble(event)

    def _on_magma_orc8r_certifier_relation_changed(self, event: RelationChangedEvent):
        if not self._certifier_relation_ready:
            self.unit.status = WaitingStatus(
                "Waiting for magma-orc8r-certifier relation to be ready"
            )
            event.defer()
            return
        if not self._orc8r_certs_mounted:
            self.unit.status = MaintenanceStatus("Mounting NMS certificates")
            self._mount_orc8r_certs()
    
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

    def _configure_pebble(self, event: PebbleReadyEvent):
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

    def _mount_orc8r_certs(self) -> None:
        """Patch the StatefulSet to include Orchestrator certs secret mount."""
        self.unit.status = MaintenanceStatus(
            "Mounting additional volumes required by the magma-orc8r-bootstrapper container"
        )
        client = Client()
        try:
            stateful_set = client.get(StatefulSet, name=self.app.name, namespace=self._namespace)
            stateful_set.spec.template.spec.volumes.extend(self._bootstrapper_volumes)  # type: ignore[attr-defined]  # noqa: E501
            stateful_set.spec.template.spec.containers[1].volumeMounts.extend(  # type: ignore[attr-defined]  # noqa: E501
                self._bootstrapper_volume_mounts
            )
            client.patch(
                StatefulSet, name=self.app.name, obj=stateful_set, namespace=self._namespace
            )
        except ApiError as e:
            logger.error(
                "Failed to mount additional volumes required by the magma-orc8r-bootstrapper "
                "container!"
            )
            raise e
        logger.info("Additional K8s resources for magma-orc8r-bootstrapper container applied!")

    @property
    def _certifier_relation_created(self) -> bool:
        return bool(self.model.get_relation("magma-orc8r-certifier"))

    @property
    def _certifier_relation_ready(self) -> bool:
        """Checks whether certifier relation is ready."""
        try:
            rel = self.model.get_relation("magma-orc8r-certifier")
            units = rel.units  # type: ignore[union-attr]
            return rel.data[next(iter(units))]["active"] == "True"  # type: ignore[union-attr]
        except (AttributeError, KeyError, StopIteration):
            return False

    @property
    def _pebble_layer(self) -> Layer:
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
    def _orc8r_certs_mounted(self) -> bool:
        """Check to see if the Orchestrator certs have already been mounted."""
        client = Client()
        statefulset = client.get(StatefulSet, name=self.app.name, namespace=self._namespace)
        return all(
            volume_mount in statefulset.spec.template.spec.containers[1].volumeMounts  # type: ignore[attr-defined]  # noqa: E501
            for volume_mount in self._bootstrapper_volume_mounts
        )

    @property
    def _bootstrapper_volumes(self) -> list:
        """Returns a list of volumes required by the magma-orc8r-bootstrapper container."""
        return [
            Volume(
                name="certs",
                secret=SecretVolumeSource(secretName="orc8r-certs"),
            ),
        ]
    
    @property
    def _db_relation_established(self) -> bool:
        """Validates that database relation is established (that there is a relation and that
        credentials have been passed)."""
        if not self._get_db_connection_string:
            return False
        return True


    @property
    def _bootstrapper_volume_mounts(self) -> list:
        """Returns a list of volume mounts required by the magma-orc8r-bootstrapper container."""
        return [
            VolumeMount(
                mountPath="/var/opt/magma/certs",
                name="certs",
                readOnly=True,
            ),
        ]
    
    @property
    def _get_db_connection_string(self):
        """Returns DB connection string provided by the DB relation."""
        try:
            db_relation = self.model.get_relation("db")
            return ConnectionString(db_relation.data[db_relation.app]["master"]) # why do we have db and master hard coded?
        except (AttributeError, KeyError):
            return None


    def _on_magma_orc8r_bootstrapper_relation_joined(self, event: RelationJoinedEvent):
        self._update_relations()
        if not self._service_is_running:
            event.defer()
            return

    def _update_relation_active_status(self, relation: Relation, is_active: bool):
        relation.data[self.unit].update(
            {
                "active": str(is_active),
            }
        )

    @property
    def _service_is_running(self) -> bool:
        if self._container.can_connect():
            try:
                self._container.get_service(self._service_name)
                return True
            except ModelError:
                pass
        return False

    def _update_relations(self):
        if not self.unit.is_leader():
            return
        relations = self.model.relations[self.meta.name]
        for relation in relations:
            self._update_relation_active_status(
                relation=relation, is_active=self._service_is_running
            )

    @property
    def _namespace(self) -> str:
        return self.model.name


if __name__ == "__main__":
    main(MagmaOrc8rBootstrapperCharm)
