#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from typing import List

import ops.lib
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from lightkube import Client
from lightkube.models.core_v1 import SecretVolumeSource, Volume, VolumeMount
from lightkube.resources.apps_v1 import StatefulSet
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer
from pgconnstr import ConnectionString  # type: ignore[import]

logger = logging.getLogger(__name__)
pgsql = ops.lib.use("pgsql", 1, "postgresql-charmers@lists.launchpad.net")


class MagmaNmsMagmalteCharm(CharmBase):

    DB_NAME = "magma_dev"

    def __init__(self, *args):
        """Creates a new instance of this object for each event."""
        super().__init__(*args)
        self._container_name = self._service_name = "magma-nms-magmalte"
        self._namespace = self.model.name
        self._container = self.unit.get_container(self._container_name)
        self._db = pgsql.PostgreSQLClient(self, "db")
        self.framework.observe(
            self.on.magma_nms_magmalte_pebble_ready, self._on_magma_nms_magmalte_pebble_ready
        )
        self.framework.observe(
            self._db.on.database_relation_joined, self._on_database_relation_joined
        )
        self.framework.observe(
            self.on.certifier_relation_changed, self._on_certifier_relation_changed
        )
        self._service_patcher = KubernetesServicePatch(self, [("magmalte", 8081, 8081)])

    def _on_magma_nms_magmalte_pebble_ready(self, event):
        if not self._relations_ready:
            event.defer()
            return
        self._configure_pebble()

    def _on_database_relation_joined(self, event):
        """Event handler for database relation change.
        - Sets the event.database field on the database joined event.
        - Required because setting the database name is only possible
          from inside the event handler per https://github.com/canonical/ops-lib-pgsql/issues/2
        - Sets our database parameters based on what was provided
          in the relation event.
        """
        db_connection_string = event.master
        if self.unit.is_leader() and db_connection_string is not None:
            event.database = self.DB_NAME
        elif event.database != self.DB_NAME or db_connection_string is None:
            event.defer()
            return

    def _on_certifier_relation_changed(self, event):
        """Mounts certificates required by the magma-nms-magmalte."""
        if not self._nms_certs_mounted:
            self.unit.status = MaintenanceStatus("Mounting NMS certificates...")
            self._mount_certifier_certs()

    def _configure_pebble(self):
        """Adds layer to pebble config if the proposed config is different from the current one."""
        self.unit.status = MaintenanceStatus(
            f"Configuring pebble layer for {self._service_name}..."
        )
        plan = self._container.get_plan()
        layer = self._pebble_layer
        if plan.services != layer.services:
            self._container.add_layer(self._container_name, layer, combine=True)
            self._container.restart(self._service_name)
            logger.info(f"Restarted container {self._service_name}")
            self.unit.status = ActiveStatus()

    def _mount_certifier_certs(self) -> None:
        """Patch the StatefulSet to include NMS certs secret mount."""
        self.unit.status = MaintenanceStatus(
            "Mounting additional volumes required by the magma-nms-magmalte container..."
        )
        client = Client()
        stateful_set = client.get(StatefulSet, name=self.app.name, namespace=self._namespace)
        stateful_set.spec.template.spec.volumes.extend(self._magma_nms_magmalte_volumes)  # type: ignore[attr-defined]  # noqa: E501
        stateful_set.spec.template.spec.containers[1].volumeMounts.extend(  # type: ignore[attr-defined]  # noqa: E501
            self._magma_nms_magmalte_volume_mounts
        )
        client.patch(StatefulSet, name=self.app.name, obj=stateful_set, namespace=self._namespace)
        logger.info("Additional K8s resources for magma-nms-magmalte container applied!")

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
                        "command": "yarn run start:prod",
                        "environment": {
                            "API_CERT_FILENAME": "/run/secrets/admin_operator.pem",
                            "API_PRIVATE_KEY_FILENAME": "/run/secrets/admin_operator.key.pem",
                            "API_HOST": f"api.{self._get_domain_name}",
                            "PORT": 8081,
                            "HOST": "0.0.0.0",
                            "MYSQL_HOST": self._get_db_connection_string.host,
                            "MYSQL_PORT": self._get_db_connection_string.port,
                            "MYSQL_DB": self._get_db_connection_string.dbname,
                            "MYSQL_USER": self._get_db_connection_string.user,
                            "MYSQL_PASS": self._get_db_connection_string.password,
                            "MAPBOX_ACCESS_TOKEN": "",
                            "MYSQL_DIALECT": "postgres",
                            "PUPPETEER_SKIP_DOWNLOAD": "true",
                            "USER_GRAFANA_ADDRESS": "orc8r-user-grafana:3000",
                        },
                    }
                },
            }
        )

    @property
    def _magma_nms_magmalte_volumes(self) -> List[Volume]:
        """Returns the additional volumes required by the magma-nms-magmalte container."""
        return [
            Volume(
                name="orc8r-secrets-certs",
                secret=SecretVolumeSource(secretName="nms-certs"),
            ),
        ]

    @property
    def _magma_nms_magmalte_volume_mounts(self) -> List[VolumeMount]:
        """Returns the additional volume mounts for the magma-nms-magmalte container."""
        return [
            VolumeMount(
                mountPath="/run/secrets/admin_operator.pem",
                name="orc8r-secrets-certs",
                subPath="admin_operator.pem",
            ),
            VolumeMount(
                mountPath="/run/secrets/admin_operator.key.pem",
                name="orc8r-secrets-certs",
                subPath="admin_operator.key.pem",
            ),
        ]

    @property
    def _relations_ready(self) -> bool:
        """Checks whether required relations are ready."""
        required_relations = ["certifier", "db"]
        missing_relations = [
            relation
            for relation in required_relations
            if not self.model.get_relation(relation)
            or len(self.model.get_relation(relation).units) == 0  # noqa: W503
        ]
        if missing_relations:
            msg = f"Waiting for relations: {', '.join(missing_relations)}"
            self.unit.status = BlockedStatus(msg)
            return False
        if not self._get_domain_name:
            self.unit.status = WaitingStatus("Waiting for certifier relation to be ready...")
            return False
        if not self._get_db_connection_string:
            self.unit.status = WaitingStatus("Waiting for db relation to be ready...")
            return False
        return True

    @property
    def _nms_certs_mounted(self) -> bool:
        """Check to see if the NMS certs have already been mounted."""
        client = Client()
        statefulset = client.get(StatefulSet, name=self.app.name, namespace=self._namespace)
        return all(
            volume_mount in statefulset.spec.template.spec.containers[1].volumeMounts  # type: ignore[attr-defined]  # noqa: E501
            for volume_mount in self._magma_nms_magmalte_volume_mounts
        )

    @property
    def _get_domain_name(self):
        """Returns domain name provided by the orc8r-certifier relation."""
        try:
            certifier_relation = self.model.get_relation("certifier")
            units = certifier_relation.units
            return certifier_relation.data[next(iter(units))]["domain"]
        except KeyError:
            return None

    @property
    def _get_db_connection_string(self):
        """Returns DB connection string provided by the DB relation."""
        try:
            db_relation = self.model.get_relation("db")
            return ConnectionString(db_relation.data[db_relation.app]["master"])
        except (AttributeError, KeyError):
            return None


if __name__ == "__main__":
    main(MagmaNmsMagmalteCharm)
