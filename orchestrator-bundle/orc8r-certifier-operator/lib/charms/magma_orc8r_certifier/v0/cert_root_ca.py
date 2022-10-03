# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Cert RootCA Library.

This library offers ways of providing and consuming a rootCA certificate.

To get started using the library, you just need to fetch the library using `charmcraft`.

```shell
cd some-charm
charmcraft fetch-lib charms.magma_orc8r_certifier.v0.cert_root_ca
```

Charms providing rootCA certificate should use `CertRootCAProvides`.
Typical usage of this class would look something like:

    ```python
    ...
    from charms.magma_orc8r_certifier.v0.cert_root_ca import CertRootCAProvides
    ...

    class SomeProviderCharm(CharmBase):

        def __init__(self, *args):
            ...
            self.cert_root_ca = CertRootCAProvides(charm=self, relationship_name="cert-root-ca")
            ...
            self.framework.observe(
                self.cert_root_ca.on.certificate_request, self._on_certificate_request
            )

        def _on_certificate_request(self, event):
            ...
            self.cert_root_ca.set_certificate(
                relation_id=event.relation_id,
                certificate=certificate,
            )
    ```

    And a corresponding section in charm's `metadata.yaml`:
    ```
    provides:
        cert-root-ca:  # Relation name
            interface: cert-root-ca  # Relation interface
    ```

Charms that require rootCA certificate should use `CertRootCARequires`.
Typical usage of this class would look something like:

    ```python
    ...
    from charms.magma_orc8r_certifier.v0.cert_root_ca import CertRootCARequires
    ...

    class SomeRequirerCharm(CharmBase):

        def __init__(self, *args):
            ...
            self.cert_root_ca = CertRootCARequires(charm=self, relationship_name="cert-root-ca")
            ...
            self.framework.observe(
                self.cert_root_ca.on.certificate_available, self._on_certificate_available
            )

        def _on_certificate_available(self, event):
            certificate = event.certificate
            # Do something with the certificate
    ```

    And a corresponding section in charm's `metadata.yaml`:
    ```
    requires:
        cert-root-ca:  # Relation name
            interface: cert-root-ca  # Relation interface
    ```
"""

from ops.charm import CharmBase, CharmEvents, RelationChangedEvent, RelationJoinedEvent
from ops.framework import EventBase, EventSource, Object

# The unique Charmhub library identifier, never change it
LIBID = "1f83c3c6b47845f8b0e2357362f57ccf"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1


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


class CertRootCAProviderCharmEvents(CharmEvents):
    """All custom events for the CertRootProvider."""

    certificate_request = EventSource(CertificateRequestEvent)


class CertRootCAProvides(Object):
    """Class to be instantiated by provider of root certificate."""

    on = CertRootCAProviderCharmEvents()

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


class CertRootCARequirerCharmEvents(CharmEvents):
    """All custom events for the CertRootRequirer."""

    certificate_available = EventSource(CertificateAvailableEvent)


class CertRootCARequires(Object):
    """Class to be instantiated by requirer of rootCA certificate."""

    on = CertRootCARequirerCharmEvents()

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
