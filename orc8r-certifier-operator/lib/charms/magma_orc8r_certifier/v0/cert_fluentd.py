# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Cert Fluentd Library.

This library offers ways of providing and consuming a fluentd certificate.

To get started using the library, you just need to fetch the library using `charmcraft`.

```shell
cd some-charm
charmcraft fetch-lib charms.magma_orc8r_certifier.v0.cert_fluentd
```

Charms providing fluentd certificate should use `CertFluentdProvides`.
Typical usage of this class would look something like:

    ```python
    ...
    from charms.magma_orc8r_certifier.v0.cert_fluentd import CertFluentdProvides
    ...

    class SomeProviderCharm(CharmBase):

        def __init__(self, *args):
            ...
            self.cert_fluentd = CertFluentdProvides(charm=self, relationship_name="cert-fluentd")
            ...
            self.framework.observe(
                self.cert_fluentd.on.certificate_request, self._on_certificate_request
            )

        def _on_certificate_request(self, event):
            ...
            self.cert_fluentd.set_certificate(
                relation_id=event.relation_id,
                certificate=certificate,
                private_key=private_key,
            )
    ```

    And a corresponding section in charm's `metadata.yaml`:
    ```
    provides:
        cert-fluentd:  # Relation name
            interface: cert-fluentd  # Relation interface
    ```

Charms that require fluentd certificate should use `CertFluentdRequires`.
Typical usage of this class would look something like:

    ```python
    ...
    from charms.magma_orc8r_certifier.v0.cert_fluentd import CertFluentdRequires
    ...

    class SomeRequirerCharm(CharmBase):

        def __init__(self, *args):
            ...
            self.cert_fluentd = CertFluentdRequires(charm=self, relationship_name="cert-fluentd")
            ...
            self.framework.observe(
                self.cert_fluentd.on.certificate_available, self._on_certificate_available
            )

        def _on_certificate_available(self, event):
            certificate = event.certificate
            private_key = event.private_key
            # Do something with the certificate and the private_key
    ```

    And a corresponding section in charm's `metadata.yaml`:
    ```
    requires:
        cert-fluentd:  # Relation name
            interface: cert-fluentd  # Relation interface
    ```
"""

from ops.charm import CharmBase, CharmEvents, RelationChangedEvent, RelationJoinedEvent
from ops.framework import EventBase, EventSource, Object

# The unique Charmhub library identifier, never change it
LIBID = "tbd"

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


class CertFluentdProviderCharmEvents(CharmEvents):
    """All custom events for the CertFluentdProvider."""

    certificate_request = EventSource(CertificateRequestEvent)


class CertFluentdProvides(Object):
    """Class to be instantiated by provider of the fluentd certificate."""

    on = CertFluentdProviderCharmEvents()

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

    def set_certificate(self, relation_id: int, certificate: str, private_key: str) -> None:
        """Sets private key in relation data.

        Args:
            relation_id (str): Relation ID
            certificate (str): Certificate
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


class CertificateAvailableEvent(EventBase):
    """Dataclass for Certificate available events."""

    def __init__(self, handle, certificate: str, private_key: str):
        """Sets certificate and private key."""
        super().__init__(handle)
        self.certificate = certificate
        self.private_key = private_key

    def snapshot(self) -> dict:
        """Returns event data."""
        return {"certificate": self.certificate, "private_key": self.private_key}

    def restore(self, snapshot):
        """Restores event data."""
        self.certificate = snapshot["certificate"]
        self.private_key = snapshot["private_key"]


class CertFluentdRequirerCharmEvents(CharmEvents):
    """All custom events for the CertFluentdRequirer."""

    certificate_available = EventSource(CertificateAvailableEvent)


class CertFluentdRequires(Object):
    """Class to be instantiated by requirer of the fluentd certificate."""

    on = CertFluentdRequirerCharmEvents()

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
        private_key = relation_data[event.unit].get("private_key")
        if certificate:
            self.on.certificate_available.emit(certificate=certificate, private_key=private_key)
