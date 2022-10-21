# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Cert Certifier Library.

## Getting started

```shell
charmcraft fetch-lib charms.magma_orc8r_certifier.v0.cert_certifier
```


### Requirer Charm

```python
class CertCertifierRequires(Object):

    on = CertCertifierRequirerCharmEvents()

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
LIBID = "3bb5a7bafc0f4631872067f4f3e9094e"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 3


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


class CertificateAvailableEvent(EventBase):
    """Dataclass for Certificate available events."""

    def __init__(self, handle, certificate: str):
        """Sets certificate."""
        super().__init__(handle)
        self.certificate = certificate

    def snapshot(self) -> dict:
        """Returns event data."""
        return {"certificate": self.certificate}

    def restore(self, snapshot):
        """Restores event data."""
        self.certificate = snapshot["certificate"]


class CertCertifierProviderCharmEvents(CharmEvents):
    """All custom events for the CertCertifierProvider."""

    certificate_request = EventSource(CertificateRequestEvent)


class CertCertifierRequirerCharmEvents(CharmEvents):
    """All custom events for the CertCertifierRequirer."""

    certificate_available = EventSource(CertificateAvailableEvent)


class CertCertifierProvides(Object):
    """Class to be instantiated by provider of certifier certificate."""

    on = CertCertifierProviderCharmEvents()

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

    def set_certificate(self, relation_id: int, certificate: str) -> None:
        """Sets private key in relation data.

        Args:
            relation_id (str): Relation ID
            certificate (str): Certificate

        Returns:
            None
        """
        relation = self.model.get_relation(
            relation_name=self.relationship_name, relation_id=relation_id
        )
        relation.data[self.model.unit]["certificate"] = certificate  # type: ignore[union-attr]

    def _on_relation_joined(self, event: RelationJoinedEvent) -> None:
        """Triggered whenever a requirer charm joins the relation.

        Args:
            event (RelationJoinedEvent): Juju event

        Returns:
            None
        """
        self.on.certificate_request.emit(relation_id=event.relation.id)


class CertCertifierRequires(Object):
    """Class to be instantiated by requirer of certifier certificate."""

    on = CertCertifierRequirerCharmEvents()

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
        certificate = relation_data[event.unit].get("certificate")
        if certificate:
            self.on.certificate_available.emit(certificate=certificate)
