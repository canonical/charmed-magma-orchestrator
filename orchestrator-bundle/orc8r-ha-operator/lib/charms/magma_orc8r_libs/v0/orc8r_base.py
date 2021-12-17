# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""# Orc8rBase Library.
This library is designed to enable developers to easily create new charms for Magma orc8r. This
library contains all the logic necessary to wait for necessary relations and be deployed.

When initialised, this library binds a handler to the parent charm's `pebble_ready`
event. This will ensure that the service is configured when this event is triggered.

The constructor simply takes the following:
- Reference to the parent charm (CharmBase)
- The service name (str)
- The startup command (str)
- Whether a database relation is needed (bool)
- The pebble Ready event method (ops.CharmEvent)

## Getting Started
To get started using the library, you just need to fetch the library using `charmcraft`. **Note
that you also need to add `ops-lib-pgsql` to your charm's `requirements.txt`.**
```shell
cd some-charm
charmcraft fetch-lib charms.magma_orc8r_libs.v0.orc8r_base
echo <<-EOF >> requirements.txt
ops-lib-pgsql
EOF
```

Then, to initialise the library:
For ClusterIP services:

```python
from ops.charm import CharmBase
from ops.main import main

from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from charms.orc8r_libs.v0.orc8r_base import Orc8rBase


class MagmaOrc8rDirectorydCharm(CharmBase):

    def __init__(self, *args):
        super().__init__(*args)
        self._service_patcher = KubernetesServicePatch(self, [("grpc", 9180, 9106)])
        startup_command = (
            "/usr/bin/envdir "
            "/var/opt/magma/envdir "
            "/var/opt/magma/bin/directoryd "
            "-logtostderr=true "
            "-v=0"
        )
        self._orc8r_base = Orc8rBase(
            self,
            service_name="magma-orc8r-directoryd",
            startup_command=startup_command,
            database_relation_needed=True,
            pebble_ready_event=self.on.magma_orc8r_directoryd_pebble_ready
        )
```

"""


import logging

import ops.lib
from ops.charm import CharmBase, CharmEvents
from ops.framework import Object
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer
from pgconnstr import ConnectionString  # type: ignore[import]

# The unique Charmhub library identifier, never change it
LIBID = "bb3ed1ffc47848b386301b42c94acac2"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 3


logger = logging.getLogger(__name__)
pgsql = ops.lib.use("pgsql", 1, "postgresql-charmers@lists.launchpad.net")


class Orc8rBase(Object):
    DB_NAME = "magma_dev"

    def __init__(
        self,
        charm: CharmBase,
        service_name: str,
        startup_command: str,
        pebble_ready_event: CharmEvents,
        database_relation_needed: bool = False,
        additional_environment_variables: dict = None,
    ):
        super().__init__(charm, "ocr8r-base")
        self._container_name = self._service_name = service_name
        self.charm = charm
        self.startup_command = startup_command
        self.database_relation_needed = database_relation_needed
        self._container = self.charm.unit.get_container(self._container_name)
        self.framework.observe(pebble_ready_event, self._on_magma_orc8r_pebble_ready)  # type: ignore[arg-type]  # noqa: E501

        if additional_environment_variables:
            self.additional_environment_variables = additional_environment_variables
        else:
            self.additional_environment_variables = {}

        if self.database_relation_needed:
            self._db = pgsql.PostgreSQLClient(self.charm, "db")  # type: ignore[attr-defined]
            self.framework.observe(
                self._db.on.database_relation_joined, self._on_database_relation_joined
            )

    def _on_magma_orc8r_pebble_ready(self, event):
        if self.database_relation_needed:
            if not self._check_db_relation_has_been_established():
                self.charm.unit.status = BlockedStatus(
                    "Waiting for database relation to be established..."
                )
                event.defer()
                return
        self._configure_orc8r(event)

    def _configure_orc8r(self, event):
        """
        Adds layer to pebble config if the proposed config is different from the current one
        """
        self.charm.unit.status = MaintenanceStatus("Configuring pod")
        pebble_layer = self._pebble_layer()
        try:
            plan = self._container.get_plan()
            if plan.services != pebble_layer.services:
                self._container.add_layer(self._container_name, pebble_layer, combine=True)
                self._container.restart(self._service_name)
                logger.info(f"Restarted container {self._service_name}")
                self.charm.unit.status = ActiveStatus()
        except ConnectionError:
            logger.error(
                f"Could not restart {self._service_name} -- Pebble socket does "
                f"not exist or is not responsive"
            )

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
                        "command": self.startup_command,
                        "environment": self._environment_variables,
                    }
                },
            }
        )

    def _on_database_relation_joined(self, event):
        """
        Event handler for database relation change.
        - Sets the event.database field on the database joined event.
        - Required because setting the database name is only possible
          from inside the event handler per https://github.com/canonical/ops-lib-pgsql/issues/2
        - Sets our database parameters based on what was provided
          in the relation event.
        """
        db_connection_string = event.master
        if self.charm.unit.is_leader() and db_connection_string is not None:
            event.database = self.DB_NAME
        elif event.database != self.DB_NAME or db_connection_string is None:
            event.defer()
            return

    def _check_db_relation_has_been_established(self):
        """Validates that database relation is ready (that there is a relation and that credentials
        have been passed)."""
        if not self._get_db_connection_string:
            self.charm.unit.status = WaitingStatus("Waiting for db relation to be ready...")
            return False
        return True

    @property
    def _get_db_connection_string(self):
        """Returns DB connection string provided by the DB relation."""
        try:
            db_relation = self.model.get_relation("db")
            return ConnectionString(db_relation.data[db_relation.app]["master"])
        except (AttributeError, KeyError):
            return None

    @property
    def _environment_variables(self):
        environment_variables = {}
        default_environment_variables = {
            "SERVICE_HOSTNAME": self._container_name,
            "HELM_RELEASE_NAME": "orc8r",
        }
        environment_variables.update(self.additional_environment_variables)
        environment_variables.update(default_environment_variables)
        if self.database_relation_needed:
            sql_environment_variables = {
                "DATABASE_SOURCE": f"dbname={self._get_db_connection_string.dbname} "
                f"user={self._get_db_connection_string.user} "
                f"password={self._get_db_connection_string.password} "
                f"host={self._get_db_connection_string.host} "
                f"sslmode=disable",
                "SQL_DRIVER": "postgres",
                "SQL_DIALECT": "psql",
                "SERVICE_HOSTNAME": self._container_name,
                "HELM_RELEASE_NAME": "orc8r",
            }
            environment_variables.update(sql_environment_variables)
        return environment_variables
