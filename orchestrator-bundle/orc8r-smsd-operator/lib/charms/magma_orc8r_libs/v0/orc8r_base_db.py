# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""# Orc8rBaseDB Library.
This library is designed to enable developers to easily create new charms for Magma orc8r that
require a relationship to a database. This library contains all the logic necessary to wait for
necessary relations and be deployed. When initialised, this library binds a handler to the parent
charm's `pebble_ready` event. This will ensure that the service is configured when this event is
triggered. The constructor simply takes the following:
- Reference to the parent charm (CharmBase)
- The startup command (str)
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
from charms.magma_orc8r_libs.v0.orc8r_base_db import Orc8rBase
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from ops.charm import CharmBase
from ops.main import main


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
        self._orc8r_base = Orc8rBase(self, startup_command=startup_command)

```
"""

import logging

import ops.lib
from ops.charm import CharmBase
from ops.framework import Object
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer
from pgconnstr import ConnectionString  # type: ignore[import]

# The unique Charmhub library identifier, never change it
LIBID = "7e1096554dd649b78acd5f3187c017c8"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 7


logger = logging.getLogger(__name__)
pgsql = ops.lib.use("pgsql", 1, "postgresql-charmers@lists.launchpad.net")


class Orc8rBase(Object):
    DB_NAME = "magma_dev"

    def __init__(
        self,
        charm: CharmBase,
        startup_command: str,
        additional_environment_variables: dict = None,
    ):
        super().__init__(charm, "orc8r-base")
        self.charm = charm
        self.startup_command = startup_command
        self._container_name = self._service_name = self.charm.meta.name
        self._container = self.charm.unit.get_container(self._container_name)
        pebble_ready_event = getattr(
            self.charm.on, f"{self._service_name.replace('-', '_')}_pebble_ready"
        )
        self.framework.observe(pebble_ready_event, self._on_magma_orc8r_pebble_ready)

        if additional_environment_variables:
            self.additional_environment_variables = additional_environment_variables
        else:
            self.additional_environment_variables = {}

        self._db = pgsql.PostgreSQLClient(self.charm, "db")
        self.framework.observe(
            self._db.on.database_relation_joined, self._on_database_relation_joined
        )

    @property
    def _db_relation_created(self) -> bool:
        """Checks whether required relations are ready."""
        if not self.model.get_relation("db"):
            return False
        return True

    def _on_magma_orc8r_pebble_ready(self, event):
        if not self._db_relation_created:
            self.charm.unit.status = BlockedStatus("Waiting for database relation to be created")
            event.defer()
            return
        if not self._db_relation_established():
            self.charm.unit.status = WaitingStatus(
                "Waiting for database relation to be established..."
            )
            event.defer()
            return
        self._configure_orc8r(event)

    def _configure_orc8r(self, event):
        """
        Adds layer to pebble config if the proposed config is different from the current one
        """
        if self._container.can_connect():
            self.charm.unit.status = MaintenanceStatus("Configuring pod")
            pebble_layer = self._pebble_layer()
            plan = self._container.get_plan()
            if plan.services != pebble_layer.services:
                self._container.add_layer(self._container_name, pebble_layer, combine=True)
                self._container.restart(self._service_name)
                logger.info(f"Restarted container {self._service_name}")
                self.charm.unit.status = ActiveStatus()
        else:
            self.charm.unit.status = WaitingStatus("Waiting for container to be ready...")
            event.defer()

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
        if self.charm.unit.is_leader():
            event.database = self.DB_NAME
        else:
            event.defer()

    def _db_relation_established(self):
        """Validates that database relation is ready (that there is a relation and that credentials
        have been passed)."""
        if not self._get_db_connection_string:
            return False
        return True

    @property
    def _get_db_connection_string(self):
        """Returns DB connection string provided by the DB relation."""
        try:
            db_relation = self.model.get_relation("db")
            return ConnectionString(db_relation.data[db_relation.app]["master"])   # type: ignore[union-attr, index]
        except (AttributeError, KeyError):
            return None

    @property
    def _environment_variables(self):
        environment_variables = {}
        default_environment_variables = {
            "SERVICE_HOSTNAME": self._container_name,
            "SERVICE_REGISTRY_MODE": "k8s",
            "SERVICE_REGISTRY_NAMESPACE": self._namespace,
        }
        environment_variables.update(self.additional_environment_variables)
        environment_variables.update(default_environment_variables)
        sql_environment_variables = {
            "DATABASE_SOURCE": f"dbname={self.DB_NAME} "
            f"user={self._get_db_connection_string.user} "
            f"password={self._get_db_connection_string.password} "
            f"host={self._get_db_connection_string.host} "
            f"sslmode=disable",
            "SQL_DRIVER": "postgres",
            "SQL_DIALECT": "psql",
            "SERVICE_HOSTNAME": self._container_name,
        }
        environment_variables.update(sql_environment_variables)
        return environment_variables

    @property
    def _namespace(self) -> str:
        return self.charm.model.name
