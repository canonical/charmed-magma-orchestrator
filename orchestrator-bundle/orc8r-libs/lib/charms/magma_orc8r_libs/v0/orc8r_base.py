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
For ClusterIP services:

```python

from charms.magma_orc8r_libs.v0.orc8r_base import Orc8rBase
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from ops.charm import CharmBase
from ops.main import main


class MagmaOrc8rHACharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self._service_patcher = KubernetesServicePatch(self, [("grpc", 9180, 9119)])
        startup_command = (
            "/usr/bin/envdir "
            "/var/opt/magma/envdir "
            "/var/opt/magma/bin/ha "
            "-logtostderr=true "
            "-v=0"
        )
        self._orc8r_base = Orc8rBase(self, startup_command=startup_command)
```

"""


import logging

from ops.charm import CharmBase
from ops.framework import Object
from ops.model import ActiveStatus, MaintenanceStatus
from ops.pebble import Layer

# The unique Charmhub library identifier, never change it
LIBID = "bb3ed1ffc47848b386301b42c94acac2"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 6


logger = logging.getLogger(__name__)


class Orc8rBase(Object):
    def __init__(
        self,
        charm: CharmBase,
        startup_command: str,
        additional_environment_variables: dict = None,
    ):
        super().__init__(charm, "orc8r-base")
        self.charm = charm
        self.startup_command = startup_command
        self._namespace = self.charm.model.name
        self._container_name = self._service_name = self.charm.meta.name
        pebble_ready_event = getattr(
            self.charm.on, f"{self._service_name.replace('-', '_')}_pebble_ready"
        )
        self._container = self.charm.unit.get_container(self._container_name)
        self.framework.observe(pebble_ready_event, self._on_magma_orc8r_pebble_ready)

        if additional_environment_variables:
            self.additional_environment_variables = additional_environment_variables
        else:
            self.additional_environment_variables = {}

    def _on_magma_orc8r_pebble_ready(self, event):
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

    @property
    def _environment_variables(self):
        environment_variables = {}
        default_environment_variables = {
            "SERVICE_HOSTNAME": self._container_name,
            "SERVICE_REGISTRY_MODE": "k8s",
            "SERVICE_REGISTRY_NAMESPACE": self._namespace
        }
        environment_variables.update(self.additional_environment_variables)
        environment_variables.update(default_environment_variables)
        return environment_variables
