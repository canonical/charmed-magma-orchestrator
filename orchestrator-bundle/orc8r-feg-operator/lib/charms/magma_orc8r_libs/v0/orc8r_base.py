# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""# Orc8rBase Library.
This library is designed to enable developers to easily create new charms for Magma orc8r. This
library contains all the logic necessary to wait for necessary relations and be deployed.
When initialised, this library binds a handler to the parent charm's `pebble_ready`
event. This will ensure that the service is configured when this event is triggered.
The constructor simply takes the following:
- Reference to the parent charm (CharmBase)
- The startup command (str)
## Getting Started
To get started using the library, you just need to fetch the library using `charmcraft`.
```shell
cd some-charm
charmcraft fetch-lib charms.magma_orc8r_libs.v0.orc8r_base
```
Then, to initialise the library:
```python
from charms.magma_orc8r_libs.v0.orc8r_base import Orc8rBase
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from ops.charm import CharmBase
from ops.main import main
class MagmaOrc8rHACharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self._service_patcher = KubernetesServicePatch(self, [("grpc", 9180)])
        startup_command = (
            "/usr/bin/envdir "
            "/var/opt/magma/envdir "
            "/var/opt/magma/bin/ha "
            "-logtostderr=true "
            "-v=0"
        )
        self._orc8r_base = Orc8rBase(self, startup_command=startup_command)
```
Charms that leverage this library also need to specify a `provides` relation in their
`metadata.yaml` file. For example:
```yaml
provides:
  magma-orc8r-ha:
    interface: magma-orc8r-ha
```
"""


import logging

from ops.charm import CharmBase
from ops.framework import Object
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
    ModelError,
    WaitingStatus,
)
from ops.pebble import Layer

# The unique Charmhub library identifier, never change it
LIBID = "bb3ed1ffc47848b386301b42c94acac2"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 11


logger = logging.getLogger(__name__)


class Orc8rBase(Object):
    def __init__(
        self,
        charm: CharmBase,
        startup_command: str,
        required_relations: list = None,
        additional_environment_variables: dict = None,
    ):
        super().__init__(charm, "orc8r-base")
        self.charm = charm
        self.startup_command = startup_command
        self.required_relations = required_relations or []
        self.container_name = self.service_name = self.charm.meta.name
        service_name_with_underscores = self.service_name.replace("-", "_")
        provided_relations = self.charm.meta.provides.keys()
        if self.container_name in provided_relations:
            service_status_relation_name = self.container_name
            service_status_relation_name_with_underscores = service_status_relation_name.replace(
                "-", "_"
            )
            relation_joined_event = getattr(
                self.charm.on, f"{service_status_relation_name_with_underscores}_relation_joined"
            )
            self.framework.observe(relation_joined_event, self._on_relation_joined)
        pebble_ready_event = getattr(
            self.charm.on, f"{service_name_with_underscores}_pebble_ready"
        )
        self.container = self.charm.unit.get_container(self.container_name)
        self.framework.observe(pebble_ready_event, self._on_magma_orc8r_pebble_ready)

        if additional_environment_variables:
            self.additional_environment_variables = additional_environment_variables
        else:
            self.additional_environment_variables = {}

    def _on_magma_orc8r_pebble_ready(self, event):
        if not self._relations_ready:
            event.defer()
            return
        self._configure_orc8r(event)

    def _configure_orc8r(self, event):
        """
        Adds layer to pebble config if the proposed config is different from the current one
        """
        if self.container.can_connect():
            self.charm.unit.status = MaintenanceStatus("Configuring pod")
            pebble_layer = self._pebble_layer()
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

    def _pebble_layer(self) -> Layer:
        """Returns pebble layer for the charm."""
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
        return environment_variables

    @property
    def namespace(self) -> str:
        return self.charm.model.name

    def _update_relations(self):
        if not self.charm.unit.is_leader():
            return
        relations = self.charm.model.relations[self.charm.meta.name]
        for relation in relations:
            self._update_relation_active_status(
                relation=relation, is_active=self._service_is_running
            )

    def _on_relation_joined(self, event):
        if not self.charm.unit.is_leader():
            return
        self._update_relation_active_status(
            relation=event.relation, is_active=self._service_is_running
        )
        if not self._service_is_running:
            event.defer()
            return

    @property
    def _service_is_running(self) -> bool:
        if self.container.can_connect():
            try:
                self.container.get_service(self.service_name)
                return True
            except ModelError:
                pass
        return False

    def _update_relation_active_status(self, relation, is_active: bool):
        relation.data[self.charm.unit].update(
            {
                "active": str(is_active),
            }
        )

    @property
    def _relations_ready(self) -> bool:
        """Checks whether required relations are ready."""
        if missing_relations := [
            relation for relation in self.required_relations if not self._relation_active(relation)
        ]:
            msg = f"Waiting for relations: {', '.join(missing_relations)}"
            self.charm.unit.status = BlockedStatus(msg)
            return False
        return True

    def _relation_active(self, relation_name: str) -> bool:
        try:
            relation = self.model.get_relation(relation_name)
            if relation:
                units = relation.units
                return relation.data[next(iter(units))]["active"] == "True"
            else:
                return False
        except (KeyError, StopIteration):
            return False
