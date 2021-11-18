#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import ops.lib
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer
from pgconnstr import ConnectionString  # type: ignore[import]

logger = logging.getLogger(__name__)
pgsql = ops.lib.use("pgsql", 1, "postgresql-charmers@lists.launchpad.net")


class MagmaOrc8rAccessdCharm(CharmBase):
    """Charm the service."""

    DB_NAME = "magma_dev"

    def __init__(self, *args):
        """Creates a new instance of this object for each event."""
        super().__init__(*args)
        self._container_name = self._service_name = "magma-orc8r-accessd"
        self._container = self.unit.get_container(self._container_name)
        self._db = pgsql.PostgreSQLClient(self, "db")  # type: ignore[attr-defined]
        self.framework.observe(
            self.on.magma_orc8r_accessd_pebble_ready, self._on_magma_orc8r_accessd_pebble_ready
        )
        self.framework.observe(
            self._db.on.database_relation_joined, self._on_database_relation_joined
        )
        self._service_patcher = KubernetesServicePatch(self, [("grpc", 9180, 9091)])

    def _on_magma_orc8r_accessd_pebble_ready(self, event):
        if not self._check_db_relation_has_been_established():
            self.unit.status = BlockedStatus("Waiting for database relation to be established")
        else:
            self.unit.status = WaitingStatus(
                "Database relation is valid, waiting on database to come up"
            )

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
            self._configure_magma_orc8r_accessd(db_connection_string)
        elif event.database != self.DB_NAME or db_connection_string is None:
            event.defer()
            return

    def _configure_magma_orc8r_accessd(self, db_conn_str):
        """Adds layer to pebble config if the proposed config is different from the current one."""
        self.unit.status = MaintenanceStatus("Configuring pod")
        plan = self._container.get_plan()
        layer = self._pebble_layer(db_conn_str)
        if plan.services != layer.services:
            self._container.add_layer(self._container_name, layer, combine=True)
            self._container.restart(self._service_name)
            logger.info(f"Restarted container {self._service_name}")
        self.unit.status = ActiveStatus()

    def _check_db_relation_has_been_established(self):
        """Validates that database relation is ready (that there is a relation and that credentials
        have been passed)."""
        if not self.model.get_relation("db"):
            return False
        return True

    def _pebble_layer(self, conn_str: ConnectionString) -> Layer:
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
                        "/var/opt/magma/bin/accessd "
                        "-logtostderr=true "
                        "-v=0",
                        "environment": {
                            "DATABASE_SOURCE": f"dbname={conn_str.dbname} "
                            f"user={conn_str.user} "
                            f"password={conn_str.password} "
                            f"host={conn_str.host} "
                            f"sslmode=disable",
                            "SQL_DRIVER": "postgres",
                            "SQL_DIALECT": "psql",
                            "SERVICE_HOSTNAME": self._container_name,
                            "SERVICE_REGISTRY_MODE": "k8s",
                            "HELM_RELEASE_NAME": "orc8r",
                            "SERVICE_REGISTRY_NAMESPACE": "orc8r",
                        },
                    },
                },
            },
        )


if __name__ == "__main__":
    main(MagmaOrc8rAccessdCharm)
