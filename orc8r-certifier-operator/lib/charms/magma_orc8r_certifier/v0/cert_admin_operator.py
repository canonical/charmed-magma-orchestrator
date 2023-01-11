# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Cert Admin Operator library.

## Getting started

```shell
charmcraft fetch-lib charms.magma_orc8r_certifier.v0.cert_admin_operator
```

### Requirer Charm

```python
class CertAdminOperatorRequires(Object):

    on = CertAdminOperatorRequirerCharmEvents()

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
        certificate = relation_data[event.unit].get("certificate")
        self.on.certificate_available.emit(certificate=certificate)

```

"""

from ops.charm import CharmBase, CharmEvents, RelationChangedEvent, RelationJoinedEvent
from ops.framework import EventBase, EventSource, Object

# The unique Charmhub library identifier, never change it
LIBID = "6ca3a0b88afc4bebafbaa49514afb18f"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 6


class CertificateRequestEvent(EventBase):
    """Dataclass for certificate request events."""

    def __init__(self, handle, relation_id: int):
        """Sets relation id."""
        super().__init__(handle)
        self.relation_id = relation_id

    def snapshot(self) -> dict:
        """Returns event data."""
        return {
            "relation_id": self.relation_id,
        }

    def restore(self, snapshot) -> None:
        """Restores event data."""
        self.relation_id = snapshot["relation_id"]


class CertificateAvailableEvent(EventBase):
    """Dataclass for certificate available events."""

    def __init__(self, handle, certificate: str, private_key: str):
        """Sets certificate and private key."""
        super().__init__(handle)
        self.certificate = certificate
        self.private_key = private_key

    def snapshot(self) -> dict:
        """Returns event data."""
        return {"certificate": self.certificate, "private_key": self.private_key}

    def restore(self, snapshot) -> None:
        """Restores event data."""
        self.certificate = snapshot["certificate"]
        self.private_key = snapshot["private_key"]


class CertAdminOperatorProviderCharmEvents(CharmEvents):
    """All custom events for the CertAdminOperatorProvider."""

    certificate_request = EventSource(CertificateRequestEvent)


class CertAdminOperatorRequirerCharmEvents(CharmEvents):
    """All custom events for the CertAdminOperatorRequirer."""

    certificate_available = EventSource(CertificateAvailableEvent)


class CertAdminOperatorProvides(Object):
    """Class to be instantiated by provider of admin operator certificates."""

    on = CertAdminOperatorProviderCharmEvents()

    def __init__(self, charm: CharmBase, relationship_name: str):
        """Observes relation joined event.

        Args:
            charm (CharmBase): Juju charm
            relationship_name (str): Relation name
        """
        self.relationship_name = relationship_name
        self.charm = charm
        super().__init__(charm, relationship_name)
        self.framework.observe(
            charm.on[relationship_name].relation_joined, self._on_relation_joined
        )

    def set_certificate(self, relation_id: int, certificate: str, private_key: str) -> None:
        """Sets certificates in relation data.

        Args:
            relation_id (str): Relation ID
            certificate (str): TLS Certificate
            private_key (str): Private Key

        Returns:
            None
        """
        relation = self.model.get_relation(
            relation_name=self.relationship_name, relation_id=relation_id
        )
        relation.data[self.model.unit]["certificate"] = certificate  # type: ignore[union-attr]
        relation.data[self.model.unit]["private_key"] = private_key  # type: ignore[union-attr]

    def _on_relation_joined(self, event: RelationJoinedEvent) -> None:
        """Triggered whenever a requirer charm joins the relation.

        Args:
            event (RelationJoinedEvent): Juju event

        Returns:
            None
        """
        self.on.certificate_request.emit(relation_id=event.relation.id)


class CertAdminOperatorRequires(Object):
    """Class to be instantiated by requirer of admin operator certificates."""

    on = CertAdminOperatorRequirerCharmEvents()

    def __init__(self, charm: CharmBase, relationship_name: str):
        """Observes relation joined and relation changed events.

        Args:
            charm (CharmBase): Juju charm
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
        certificate = relation_data[event.unit].get("certificate")  # type: ignore[index]
        private_key = relation_data[event.unit].get("private_key")  # type: ignore[index]
        if certificate and private_key:
            self.on.certificate_available.emit(certificate=certificate, private_key=private_key)
