# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Library for the magma-orchestrator relation.

This library contains the Requires and Provides classes for handling the magma-orchestrator
interface.

## Getting Started
From a charm directory, fetch the library using `charmcraft`:

```shell
charmcraft fetch-lib charms.magma_orchestrator_interface.v0.magma_orchestrator_interface
```

Add the following libraries to the charm's `requirements.txt` file:
- jsonschema

### Requirer charm
The requirer charm is the charm requiring to connect to an instance of Magma Orchestrator
from another charm that provides this interface.

Example:
```python

from ops.charm import CharmBase
from ops.main import main

from lib.charms.magma_orchestrator_interface.v0.magma_orchestrator_interface import (
    OrchestratorAvailableEvent,
    OrchestratorRequires,
)


class DummyMagmaOrchestratorRequirerCharm(CharmBase):

    def __init__(self, *args):
        super().__init__(*args)
        self.orchestrator_requirer = OrchestratorRequires(self, "orchestrator")
        self.framework.observe(
            self.orchestrator_requirer.on.orchestrator_available, self._on_orchestrator_available
        )

    def _on_orchestrator_available(self, event: OrchestratorAvailableEvent):
        print(event.root_ca_certificate)
        print(event.orchestrator_address)
        print(event.orchestrator_port)
        print(event.bootstrapper_address)
        print(event.orchestrator_port)
        print(event.fluentd_address)
        print(event.fluentd_port)


if __name__ == "__main__":
    main(DummyMagmaOrchestratorRequirerCharm)
```

### Provider charm
The provider charm is the charm providing information about a Magma Orchestrator
for another charm that requires this interface.

Example:
```python
from ops.charm import CharmBase, RelationJoinedEvent
from ops.main import main

from lib.charms.magma_orchestrator_interface.v0.magma_orchestrator_interface import (
    OrchestratorProvides,
)


class DummyMagmaOrchestratorProviderCharm(CharmBase):

    def __init__(self, *args):
        super().__init__(*args)
        self.orchestrator_provider = OrchestratorProvides(self, "orchestrator")
        self.framework.observe(
            self.on.orchestrator_relation_joined, self._on_orchestrator_relation_joined
        )

    def _on_orchestrator_relation_joined(self, event: RelationJoinedEvent):
        if self.unit.is_leader():
            self.orchestrator_provider.set_orchestrator_information(
                root_ca_certificate="whatever certificate content",
                orchestrator_address="http://orchestrator.com",
                orchestrator_port=1234,
                bootstrapper_address="http://bootstrapper.com",
                bootstrapper_port=5678,
                fluentd_address="http://fluentd.com",
                fluentd_port=9112,
            )


if __name__ == "__main__":
    main(DummyMagmaOrchestratorProviderCharm)
```

"""


import logging

from jsonschema import exceptions, validate  # type: ignore[import]
from ops.charm import CharmBase, CharmEvents, RelationChangedEvent
from ops.framework import EventBase, EventSource, Handle, Object

# The unique Charmhub library identifier, never change it
LIBID = "ec30058c7c6d4850aba6a132d2506efe"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 2


logger = logging.getLogger(__name__)

REQUIRER_JSON_SCHEMA = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "title": "`magma-orchestrator` requirer root schema",
    "type": "object",
    "description": "The `magma-orchestrator` root schema comprises the entire requirer databag for this interface.",  # noqa: E501
    "examples": [
        {
            "root_ca_certificate": "-----BEGIN CERTIFICATE-----\nMIICvDCCAaQCFFPAOD7utDTsgFrm0vS4We18OcnKMA0GCSqGSIb3DQEBCwUAMCAx\nCzAJBgNVBAYTAlVTMREwDwYDVQQDDAh3aGF0ZXZlcjAeFw0yMjA3MjkyMTE5Mzha\nFw0yMzA3MjkyMTE5MzhaMBUxEzARBgNVBAMMCmJhbmFuYS5jb20wggEiMA0GCSqG\nSIb3DQEBAQUAA4IBDwAwggEKAoIBAQDVpcfcBOnFuyZG+A2WQzmaBI5NXgwTCfvE\neKciqRQXhzJdUkEg7eqwFrK3y9yjhoiB6q0WNAeR+nOdS/Cw7layRtGz5skOq7Aa\nN4FZHg0or30i7Rrx7afJcGJyLpxfK/OfLmJm5QEdLXV0DZp0L5vuhhEb1EUOrMaY\nGe4iwqTyg6D7fuBili9dBVn9IvNhYMVgtiqkWVLTW4ChE0LgES4oO3rQZgp4dtM5\nsp6KwHGO766UzwGnkKRizaqmLylfVusllWNPFfp6gEaxa45N70oqGUrvGSVHWeHf\nfvkhpWx+wOnu+2A5F/Yv3UNz2v4g7Vjt7V0tjL4KMV9YklpRjTh3AgMBAAEwDQYJ\nKoZIhvcNAQELBQADggEBAChjRzuba8zjQ7NYBVas89Oy7u++MlS8xWxh++yiUsV6\nWMk3ZemsPtXc1YmXorIQohtxLxzUPm2JhyzFzU/sOLmJQ1E/l+gtZHyRCwsb20fX\nmphuJsMVd7qv/GwEk9PBsk2uDqg4/Wix0Rx5lf95juJP7CPXQJl5FQauf3+LSz0y\nwF/j+4GqvrwsWr9hKOLmPdkyKkR6bHKtzzsxL9PM8GnElk2OpaPMMnzbL/vt2IAt\nxK01ZzPxCQCzVwHo5IJO5NR/fIyFbEPhxzG17QsRDOBR9fl9cOIvDeSO04vyZ+nz\n+kA2c3fNrZFAtpIlOOmFh8Q12rVL4sAjI5mVWnNEgvI=\n-----END CERTIFICATE-----\n",  # noqa: E501
            "orchestrator_address": "http://orchestrator.com",
            "orchestrator_port": "1234",
            "bootstrapper_address": "http://bootstrapper.com",
            "bootstrapper_port": "5678",
            "fluentd_address": "http://fluentd.com",
            "fluentd_port": "9112",
        }
    ],
    "properties": {
        "root_ca_certificate": {
            "type": "string",
        },
        "orchestrator_address": {
            "type": "string",
            "format": "uri",
        },
        "orchestrator_port": {
            "type": "string",
        },
        "bootstrapper_address": {
            "type": "string",
            "format": "uri",
        },
        "bootstrapper_port": {
            "type": "string",
        },
        "fluentd_address": {
            "type": "string",
            "format": "uri",
        },
        "fluentd_port": {
            "type": "string",
        },
    },
    "required": [
        "root_ca_certificate",
        "orchestrator_address",
        "orchestrator_port",
        "bootstrapper_address",
        "bootstrapper_port",
        "fluentd_address",
        "fluentd_port",
    ],
    "additionalProperties": True,
}


class OrchestratorAvailableEvent(EventBase):
    """Charm Event triggered when a Orchestrator is available."""

    def __init__(
        self,
        handle: Handle,
        root_ca_certificate: str,
        orchestrator_address: str,
        orchestrator_port: int,
        bootstrapper_address: str,
        bootstrapper_port: int,
        fluentd_address: str,
        fluentd_port: int,
    ):
        """Init."""
        super().__init__(handle)
        self.root_ca_certificate = root_ca_certificate
        self.orchestrator_address = orchestrator_address
        self.orchestrator_port = orchestrator_port
        self.bootstrapper_address = bootstrapper_address
        self.bootstrapper_port = bootstrapper_port
        self.fluentd_address = fluentd_address
        self.fluentd_port = fluentd_port

    def snapshot(self) -> dict:
        """Returns snapshot."""
        return {
            "root_ca_certificate": self.root_ca_certificate,
            "orchestrator_address": self.orchestrator_address,
            "orchestrator_port": self.orchestrator_port,
            "bootstrapper_address": self.bootstrapper_address,
            "bootstrapper_port": self.bootstrapper_port,
            "fluentd_address": self.fluentd_address,
            "fluentd_port": self.fluentd_port,
        }

    def restore(self, snapshot: dict):
        """Restores snapshot."""
        self.root_ca_certificate = snapshot["root_ca_certificate"]
        self.orchestrator_address = snapshot["orchestrator_address"]
        self.orchestrator_port = snapshot["orchestrator_port"]
        self.bootstrapper_address = snapshot["bootstrapper_address"]
        self.bootstrapper_port = snapshot["bootstrapper_port"]
        self.fluentd_address = snapshot["fluentd_address"]
        self.fluentd_port = snapshot["fluentd_port"]


class OrchestratorRequirerCharmEvents(CharmEvents):
    """List of events that the Orchestrator requirer charm can leverage."""

    orchestrator_available = EventSource(OrchestratorAvailableEvent)


class OrchestratorRequires(Object):
    """Class to be instantiated by charms requiring connectivity with Orchestrator."""

    on = OrchestratorRequirerCharmEvents()

    def __init__(self, charm: CharmBase, relationship_name: str):
        """Init."""
        super().__init__(charm, relationship_name)
        self.charm = charm
        self.relationship_name = relationship_name
        self.framework.observe(
            charm.on[relationship_name].relation_changed, self._on_relation_changed
        )

    @staticmethod
    def _relation_data_is_valid(remote_app_relation_data: dict) -> bool:
        try:
            validate(instance=remote_app_relation_data, schema=REQUIRER_JSON_SCHEMA)
            return True
        except exceptions.ValidationError:
            return False

    def _on_relation_changed(self, event: RelationChangedEvent) -> None:
        """Handler triggerred on relation changed events.

        Args:
            event: Juju event

        Returns:
            None
        """
        relation = self.model.get_relation(self.relationship_name)
        if not relation:
            logger.warning(f"No relation: {self.relationship_name}")
            return
        if not relation.app:
            logger.warning(f"No remote application in relation: {self.relationship_name}")
            return
        remote_app_relation_data = relation.data[relation.app]
        if not self._relation_data_is_valid(dict(remote_app_relation_data)):
            logger.warning(
                f"Provider relation data did not pass JSON Schema validation: "
                f"{event.relation.data[event.app]}"
            )
            return
        self.on.orchestrator_available.emit(
            root_ca_certificate=remote_app_relation_data["root_ca_certificate"],
            orchestrator_address=remote_app_relation_data["orchestrator_address"],
            orchestrator_port=int(remote_app_relation_data["orchestrator_port"]),
            bootstrapper_address=remote_app_relation_data["bootstrapper_address"],
            bootstrapper_port=int(remote_app_relation_data["bootstrapper_port"]),
            fluentd_address=remote_app_relation_data["fluentd_address"],
            fluentd_port=int(remote_app_relation_data["fluentd_port"]),
        )


class OrchestratorProvides(Object):
    """Class to be instantiated by charms providing connectivity with Orchestrator."""

    def __init__(self, charm: CharmBase, relationship_name: str):
        """Init."""
        super().__init__(charm, relationship_name)
        self.relationship_name = relationship_name
        self.charm = charm

    @staticmethod
    def port_is_valid(port_number: int) -> bool:
        """Returns whether network port is a valid number."""
        if port_number < 1 or port_number > 65535:
            return False
        return True

    def set_orchestrator_information(
        self,
        root_ca_certificate: str,
        orchestrator_address: str,
        bootstrapper_address: str,
        fluentd_address: str,
        orchestrator_port: int = 443,
        bootstrapper_port: int = 443,
        fluentd_port: int = 24224,
    ):
        """Sets orchestrator information in application relation data.

        Args:
            root_ca_certificate: Orchestrator Root CA Certificate
            orchestrator_address: Orchestrator address (ex. controller.yourdomain.com)
            bootstrapper_address: Bootstrapper address (ex. bootstrapper-controller.yourdomain.com)
            fluentd_address: Fluentd Address (ex. fluentd.yourdomain.com)
            orchestrator_port: Orchestrator port (Default: 443)
            bootstrapper_port: Bootstrapper port (Default: 443)
            fluentd_port: Fluentd port (Default: 24224)

        Returns:
            None
        """
        if not self.charm.unit.is_leader():
            raise RuntimeError("Unit must be leader to set application relation data.")
        if not self.port_is_valid(orchestrator_port):
            raise ValueError("Orchestrator port is invalid")
        if not self.port_is_valid(bootstrapper_port):
            raise ValueError("Bootstrapper port is invalid")
        if not self.port_is_valid(fluentd_port):
            raise ValueError("Fluentd port is invalid")
        relation = self.model.get_relation(self.relationship_name)
        if not relation:
            raise RuntimeError(f"Relation {self.relationship_name} not yet created")
        relation.data[self.charm.app].update(
            {
                "root_ca_certificate": root_ca_certificate,
                "orchestrator_address": orchestrator_address,
                "orchestrator_port": str(orchestrator_port),
                "bootstrapper_address": bootstrapper_address,
                "bootstrapper_port": str(bootstrapper_port),
                "fluentd_address": fluentd_address,
                "fluentd_port": str(fluentd_port),
            }
        )
