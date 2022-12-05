# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Fluentd certificates library.

This library offers a way of providing and requesting certificates for Fluentd.

To get started, fetch the library using `charmcraft`:

```shell
cd <charm directory>
charmcraft fetch-lib charms.fluentd_certificate.v0.fluentd_certificate
```

Charms providing Fluentd certificate should use `CertFluentdProvides`.
Typical usage of this class would look something like:

```python
    ...
    from charms.fluentd_certificate.v0.fluentd_certificate import CertFluentdProvides
    ...
    
    # TODO: Fill in with code example.
    
```
And a corresponding section in charm's `metadata.yaml`:

```yaml
provides:
    cert-fluentd:  # Relation name
        interface: cert-fluentd  # Relation interface
```


Charms requiring Fluentd certificate should use `FluentdCertificateRequires`.
Typical usage of this class would look something like:

```python
    ...
    from charms.fluentd_certificate.v0.fluentd_certificate import FluentdCertificateRequires
    ...
    
   # TODO: Fill in with code example.

And a corresponding section in charm's `metadata.yaml`:
```yaml
requires:
    cert-fluentd:  # Relation name
        interface: cert-fluentd  # Relation interface
```

"""

from typing import Union
from ops.charm import CharmBase, CharmEvents, RelationChangedEvent, RelationJoinedEvent
from ops.framework import EventBase, EventSource, Object

# The unique Charmhub library identifier, never change it
LIBID = "TBD"  # TODO: Publish and set LIBID

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

class FluentdCertificateAvailableEvent(EventBase):
     """Dataclass for Fluentd Certificate available events."""

     def __init__(self, handle, certificate: str):
         """Sets Fluentd certificate `fluentd.pem`."""
         super().__init__(handle)
         self.certificate = certificate

     def snapshot(self) -> dict:
         """Returns event data."""
         return {"certificate": self.certificate}

     def restore(self, snapshot):
         """Restores event data."""
         self.certificate = snapshot["certificate"]
        
class FluentdCertificateProviderCharmEvents(CharmEvents):
    """Custom events for the FluentdCertificateProvider."""

    fluentd_certificate_available = EventSource(FluentdCertificateAvailableEvent)


class FluentdCertProvides(Object):
    """Class to be instantiated by the Fluentd certificate provider."""

    on = FluentdCertificateProviderCharmEvents()
    
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

    def set_fluentd_certificate(self, relation_id: int, certificate: str) -> None:
        """Sets Fluentd certificate `fluentd.pem` in relation data.
        
        Args:
            relation_id (int): Relation id
            certificate (str): Certificate

        Returns:
            None
        """
        relation = self.model.get_relation(
            relation_name=self.relationship_name, relation_id=relation_id
        )
        relation.data[self.model.unit]["certificate"] = certificate

    def _on_relation_joined(self, event: RelationJoinedEvent) -> None:
        """Triggered whenever a requirer charm joins the relation.
        Args:
            event (RelationJoinedEvent): Juju event
        Returns:
            None
        """
        self.on.fluentd_certificate_available.emit(relation_id=event.relation.id)


class FluentdCertificateSigningRequestEvent(EventBase):
    """Dataclass for Certificate Signing Request Event."""

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


class FluentdCertificateRequirerCharmEvents(CharmEvents):
    """Custom events for the FluentdCertRequirer."""
    
    fluentd_certificate_available = EventSource(FluentdCertificateAvailableEvent)


class FluentdCertificateRequires(Object):
    """Class to be instantiated by requirer charm of the fluentd certificate."""

    on = FluentdCertificateRequirerCharmEvents()
    
    def __init__(self, charm: CharmBase, relationship_name: str):
        """Observes relation joined and relation changed events 
        Args:
            charm: Juju charm
            relationship_name (str): Relation name
        """
        self.relationship_name = relationship_name
        self.charm = charm
        super().__init__(charm, relationship_name)
        self.framework.observe(
            charm.on[relationship_name].relation_joined, self._relation_joined_event
        )
        self.framework.observe(
            charm.on[relationship_name].relation_changed, self._relation_joined_event
        )
         
    def set_certificate_signing_request(self, certificate_signing_request: str) -> None:
        """Sets Fluentd certificate signing request `fluentd.csr` in relation data.
        
        Args:
            relation_id (int): Relation id
            certificate_signing_request(str): Certificate signing request

        Returns:
            None
        """
        relation = self.model.get_relation(
            relation_name=self.relationship_name
        )
        relation.data[self.model.unit]["certificate-signing-request"] = certificate_signing_request

    def _relation_joined_event(
         self, event: Union[RelationChangedEvent, RelationJoinedEvent]
     ) -> None:
         """Triggered everytime there is a change in relation data.

         Args:
             event: Juju event (RelationChangedEvent or RelationJoinedEvent)

         Returns:
             None
         """
         if certificate_signing_request := event.relation.data[event.unit].get("certificate-signing-request"):
             self.on.certificate_signing_request_available.emit(certificate_signing_request=certificate_signing_request)