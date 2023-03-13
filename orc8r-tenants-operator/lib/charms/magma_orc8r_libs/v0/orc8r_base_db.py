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
charmcraft fetch-lib charms.magma_orc8r_libs.v0.orc8r_base_db
echo <<-EOF >> requirements.txt
ops-lib-pgsql
EOF
```
Then, to initialise the library:
```python
from charms.magma_orc8r_libs.v0.orc8r_base_db import Orc8rBase
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from ops.charm import CharmBase
from ops.main import main


class MagmaOrc8rDirectorydCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self._service_patcher = KubernetesServicePatch(self, [("grpc", 9180)])
        startup_command = (
            "/usr/bin/envdir "
            "/var/opt/magma/envdir "
            "/var/opt/magma/bin/directoryd "
            "-logtostderr=true "
            "-v=0"
        )
        self._orc8r_base = Orc8rBase(self, startup_command=startup_command)

```

Charms that leverage this library also need to specify a `provides` relation in their
`metadata.yaml` file. For example:

```yaml
provides:
  magma-orc8r-directoryd:
    interface: magma-orc8r-directoryd
```

"""

import logging
from typing import Optional, Union

import ops.lib
import psycopg2  # type: ignore[import]
from ops.charm import (
    CharmBase,
    PebbleReadyEvent,
    RelationBrokenEvent,
    RelationJoinedEvent,
    UpgradeCharmEvent,
)
from ops.framework import Object
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

# The unique Charmhub library identifier, never change it
LIBID = "7e1096554dd649b78acd5f3187c017c8"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 14


logger = logging.getLogger(__name__)
pgsql = ops.lib.use("pgsql", 1, "postgresql-charmers@lists.launchpad.net")


class Orc8rBase(Object):
    """Instantiated by Orchestrator charms that require connection with a DB."""

    DB_NAME = "magma_dev"

    def __init__(
        self,
        charm: CharmBase,
        startup_command: str,
        additional_environment_variables: dict = None,  # type: ignore[assignment]
    ):
        """Observes common events for all Orchestrator charms."""
        super().__init__(charm, "orc8r-base")
        self.charm = charm
        self.startup_command = startup_command
        self.container_name = self.service_name = self.charm.meta.name
        self.container = self.charm.unit.get_container(self.container_name)
        service_name_with_underscores = self.service_name.replace("-", "_")
        provided_relation_name = list(self.charm.meta.provides.keys())[0]
        provided_relation_name_with_underscores = provided_relation_name.replace("-", "_")
        pebble_ready_event = getattr(
            self.charm.on, f"{service_name_with_underscores}_pebble_ready"
        )
        relation_joined_event = getattr(
            self.charm.on, f"{provided_relation_name_with_underscores}_relation_joined"
        )
        self.framework.observe(pebble_ready_event, self._configure_workload)
        self.framework.observe(self.charm.on.upgrade_charm, self._configure_workload)

        if additional_environment_variables:
            self.additional_environment_variables = additional_environment_variables
        else:
            self.additional_environment_variables = {}

        self.db = pgsql.PostgreSQLClient(self.charm, "db")
        self.framework.observe(
            self.db.on.database_relation_joined, self._on_database_relation_joined
        )
        self.framework.observe(
            self.db.on.database_relation_broken, self._on_database_relation_broken
        )
        self.framework.observe(relation_joined_event, self._on_relation_joined)

    def _configure_workload(self, event: Union[PebbleReadyEvent, UpgradeCharmEvent]) -> None:
        """If database relation is ready, configures workload.

        Args:
            event: Juju event (PebbleReadyEvent or UpgradeCharmEvent)
        """
        if not self._db_relation_created:
            self.charm.unit.status = BlockedStatus("Waiting for db relation to be created")
            event.defer()
            return
        if not self._db_relation_ready:
            self.charm.unit.status = WaitingStatus("Waiting for db relation to be ready")
            event.defer()
            return
        self._configure_pebble(event)

    def _on_relation_joined(self, event: RelationJoinedEvent) -> None:
        """Triggered whenever a requirer charm joins the relation provided this charm.

        When requirer charm joins the relation, the provider charm sets its workload service
        status in the relation data bag. This allows the requirer charm to know if its
        dependency is ready or not.

        Args:
            event: Juju event (RelationJoinedEvent)
        """
        if not self.charm.unit.is_leader():
            return
        self._update_relation_active_status(
            relation=event.relation, is_active=self._service_is_running
        )

    def _on_database_relation_joined(self, event: RelationJoinedEvent) -> None:
        """Event handler for database relation change.

        - Sets the event.database field on the database joined event.
        - Required because setting the database name is only possible
          from inside the event handler per https://github.com/canonical/ops-lib-pgsql/issues/2
        - Sets our database parameters based on what was provided
          in the relation event.

        Args:
            event: Juju event (RelationJoinedEvent)
        """
        if self.charm.unit.is_leader():
            event.database = self.DB_NAME  # type: ignore[attr-defined]

    def _on_database_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Event handler for database relation broken.

        Args:
            event (RelationJoinedEvent): Juju event
        """
        self.charm.unit.status = BlockedStatus("Waiting for db relation to be created")

    def _configure_pebble(self, event: Union[PebbleReadyEvent, UpgradeCharmEvent]) -> None:
        """Adds layer to pebble config if the proposed config is different from the current one.

        Args:
            event: Juju event (PebbleReadyEvent or RelationJoinedEvent)
        """
        if self.container.can_connect():
            self.charm.unit.status = MaintenanceStatus("Configuring pod")
            pebble_layer = self._pebble_layer
            plan = self.container.get_plan()
            if plan.services != pebble_layer.services:
                self.container.add_layer(self.container_name, pebble_layer, combine=True)
                self.container.restart(self.service_name)
                logger.info(f"Restarted container {self.service_name}")
                self._update_relations()
            self.charm.unit.status = ActiveStatus()
        else:
            self.charm.unit.status = WaitingStatus("Waiting for container to be ready...")
            event.defer()

    def _update_relations(self) -> None:
        """Updates relation provided by the charm with the workload service status."""
        if not self.charm.unit.is_leader():
            return
        relations = self.charm.model.relations[self.charm.meta.name]
        for relation in relations:
            self._update_relation_active_status(
                relation=relation, is_active=self._service_is_running
            )

    @property
    def _db_relation_ready(self) -> bool:
        """Validates that database relation is ready.

        Validates that there is a relation, credentials have been passed and the database can be
        connected to.

        Returns:
            bool: Whether a database relation is ready
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
            )
            return True
        except psycopg2.OperationalError:
            return False

    @property
    def _get_db_connection_string(self) -> Optional[ConnectionString]:
        """Returns DB connection string provided by the DB relation.

        Returns:
            ConnectionString: DB connection string
        """
        try:
            db_relation = self.model.get_relation("db")
            return ConnectionString(db_relation.data[db_relation.app]["master"])  # type: ignore[index, union-attr]  # noqa: E501
        except (AttributeError, KeyError):
            return None

    @property
    def _db_relation_created(self) -> bool:
        """Checks whether required relations are ready.

        Returns:
            bool: Whether required relations are ready
        """
        if not self.model.get_relation("db"):
            return False
        return True

    @property
    def _service_is_running(self) -> bool:
        """Retrieves the workload service and returns whether it is running.

        Returns:
            bool: Whether service is running
        """
        if self.container.can_connect():
            try:
                self.container.get_service(self.service_name)
                return True
            except ModelError:
                pass
        return False

    def _update_relation_active_status(self, relation: Relation, is_active: bool) -> None:
        """Updates service status in the relation data bag.

        Args:
            relation: Juju Relation object to update
            is_active: Workload service status
        """
        relation.data[self.charm.unit].update(
            {
                "active": str(is_active),
            }
        )

    @property
    def _pebble_layer(self) -> Layer:
        """Returns pebble layer for the charm.

        Returns:
            Layer: Pebble Layer
        """
        return Layer(
            {
                "summary": f"{self.service_name} layer",
                "description": f"pebble config layer for {self.service_name}",
                "services": {
                    self.service_name: {
                        "override": "replace",
                        "summary": self.service_name,
                        "startup": "enabled",
                        "command": self.startup_command,
                        "environment": self._environment_variables,
                    }
                },
            }
        )

    @property
    def _environment_variables(self):
        environment_variables = {}
        default_environment_variables = {
            "SERVICE_HOSTNAME": self.container_name,
            "SERVICE_REGISTRY_MODE": "k8s",
            "SERVICE_REGISTRY_NAMESPACE": self.namespace,
        }
        environment_variables.update(self.additional_environment_variables)
        environment_variables.update(default_environment_variables)
        sql_environment_variables = {
            "DATABASE_SOURCE": f"dbname={self.DB_NAME} "  # type: ignore[union-attr]
            f"user={self._get_db_connection_string.user} "
            f"password={self._get_db_connection_string.password} "
            f"host={self._get_db_connection_string.host} "
            f"sslmode=disable",
            "SQL_DRIVER": "postgres",
            "SQL_DIALECT": "psql",
            "SERVICE_HOSTNAME": self.container_name,
        }
        environment_variables.update(sql_environment_variables)
        return environment_variables

    @property
    def namespace(self) -> str:
        """Returns Kubernetes namespace.

        Returns:
            str: Kubernetes namespace
        """
        return self.charm.model.name
