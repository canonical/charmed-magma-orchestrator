# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Cert Bootstrapper Library.

## Getting started

```shell
charmcraft fetch-lib charms.magma_orc8r_certifier.v0.cert_bootstrapper
```


### Requirer Charm

```python
class CertBootstrapperRequires(Object):

    on = CertBootstrapperRequirerCharmEvents()

    def __init__(self, charm, relationship_name: str):
        self.relationship_name = relationship_name
        self.charm = charm
        super().__init__(charm, relationship_name)
        self.framework.observe(
            charm.on[relationship_name].relation_joined, self._on_relation_changed
        )
        self.framework.observe(
            charm.on[relationship_name].relation_changed, self._on_relation_changed
        )

    def _on_relation_changed(self, event):
        relation_data = event.relation.data
        private_key = relation_data[event.unit].get("private_key")
        self.on.private_key_available.emit(private_key=private_key)

```

"""

from ops.charm import CharmBase, CharmEvents, RelationChangedEvent, RelationJoinedEvent
from ops.framework import EventBase, EventSource, Object

# The unique Charmhub library identifier, never change it
LIBID = "f1bec0130d964fedbb15a8b551d1b1e3"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 2


class CertificateRequestEvent(EventBase):
    """Dataclass for Certificate request events."""

    def __init__(self, handle, relation_id: int):
        """Sets relation id."""
        super().__init__(handle)
        self.relation_id = relation_id

    def snapshot(self) -> dict:
        """Returns event data."""
        return {
            "relation_id": self.relation_id,
        }

    def restore(self, snapshot):
        """Restores event data."""
        self.relation_id = snapshot["relation_id"]


class PrivateKeyAvailableEvent(EventBase):
    """Dataclass for Certificate available events."""

    def __init__(self, handle, private_key: str):
        """Sets private key."""
        super().__init__(handle)
        self.private_key = private_key

    def snapshot(self) -> dict:
        """Returns event data."""
        return {"private_key": self.private_key}

    def restore(self, snapshot):
        """Restores event data."""
        self.private_key = snapshot["private_key"]


class CertBootstrapperProviderCharmEvents(CharmEvents):
    """All custom events for the CertBootstrapperProvider."""

    private_key_request = EventSource(CertificateRequestEvent)


class CertBootstrapperRequirerCharmEvents(CharmEvents):
    """All custom events for the CertBootstrapperRequirer."""

    private_key_available = EventSource(PrivateKeyAvailableEvent)


class CertBootstrapperProvides(Object):
    """Class to be instantiated by provider of bootstrapper private key."""

    on = CertBootstrapperProviderCharmEvents()

    def __init__(self, charm: CharmBase, relationship_name: str):
        """Observes relation joined event.

        Args:
            charm: Juju charm
            relationship_name (str): Relation name
        """
        self.relationship_name = relationship_name
        self.charm = charm
        super().__init__(charm, relationship_name)
        self.framework.observe(
            charm.on[relationship_name].relation_joined, self._on_relation_joined
        )

    def set_private_key(self, relation_id: int, private_key: str) -> None:
        """Sets private key in relation data.

        Args:
            relation_id (str): Relation ID
            private_key (str): Private Key

        Returns:
            None
        """
        relation = self.model.get_relation(
            relation_name=self.relationship_name, relation_id=relation_id
        )
        relation.data[self.model.unit]["private_key"] = private_key  # type: ignore[union-attr]

    def _on_relation_joined(self, event: RelationJoinedEvent) -> None:
        """Triggered whenever a requirer charm joins the relation.

        Args:
            event (RelationJoinedEvent): Juju event

        Returns:
            None
        """
        self.on.private_key_request.emit(relation_id=event.relation.id)


class CertBootstrapperRequires(Object):
    """Class to be instantiated by requirer of bootstrapper private key."""

    on = CertBootstrapperRequirerCharmEvents()

    def __init__(self, charm: CharmBase, relationship_name: str):
        """Observes relation joined and relation changed events.

        Args:
            charm: Juju charm
            relationship_name (str): Relation name
        """
        self.relationship_name = relationship_name
        self.charm = charm
        super().__init__(charm, relationship_name)
        self.framework.observe(
            charm.on[relationship_name].relation_joined, self._on_relation_changed
        )
        self.framework.observe(
            charm.on[relationship_name].relation_changed, self._on_relation_changed
        )

    def _on_relation_changed(self, event: RelationChangedEvent) -> None:
        """Triggered everytime there's a change in relation data.

        Args:
            event (RelationChangedEvent): Juju event

        Returns:
            None
        """
        relation_data = event.relation.data
        private_key = relation_data[event.unit].get("private_key")
        if private_key:
            self.on.private_key_available.emit(private_key=private_key)
