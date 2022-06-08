"""TODO: Add a proper docstring here.

This is a placeholder docstring for this charm library. Docstrings are
presented on Charmhub and updated whenever you push a new version of the
library.

Complete documentation about creating and documenting libraries can be found
in the SDK docs at https://juju.is/docs/sdk/libraries.

See `charmcraft publish-lib` and `charmcraft fetch-lib` for details of how to
share and consume charm libraries. They serve to enhance collaboration
between charmers. Use a charmer's libraries for classes that handle
integration with their charm.

Bear in mind that new revisions of the different major API versions (v0, v1,
v2 etc) are maintained independently.  You can continue to update v0 and v1
after you have pushed v3.

Markdown is supported, following the CommonMark specification.
"""

# The unique Charmhub library identifier, never change it
LIBID = "e3a4c1b0e5554ea8aba12411943badf3"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1



import logging

from ops.charm import CharmEvents
from ops.framework import EventBase, EventSource, Object


logger = logging.getLogger(__name__)


class CertificateRequestEvent(EventBase):
    def __init__(self, handle, relation_id: int):
        super().__init__(handle)
        self.relation_id = relation_id

    def snapshot(self):
        return {
            "relation_id": self.relation_id,
        }

    def restore(self, snapshot):
        self.relation_id = snapshot["relation_id"]


class CertificateAvailableEvent(EventBase):
    def __init__(self, handle, certificate: str, private_key: str):
        super().__init__(handle)
        self.certificate = certificate
        self.private_key = private_key

    def snapshot(self):
        return {
            "certificate": self.certificate,
            "private_key": self.private_key
        }

    def restore(self, snapshot):
        self.certificate = snapshot["certificate"]
        self.private_key = snapshot["private_key"]


class CertControllerProviderCharmEvents(CharmEvents):
    certificate_request = EventSource(CertificateRequestEvent)


class CertControllerRequirerCharmEvents(CharmEvents):
    certificate_available = EventSource(CertificateAvailableEvent)


class CertControllerProvides(Object):

    on = CertControllerProviderCharmEvents()

    def __init__(self, charm, relationship_name: str):
        self.relationship_name = relationship_name
        self.charm = charm
        super().__init__(charm, relationship_name)
        self.framework.observe(
            charm.on[relationship_name].relation_joined, self._on_relation_joined
        )
        self.certificate = None

    def set_certificate(self, relation_id: int, certificate: str, private_key: str):
        relation = self.model.get_relation(
            relation_name=self.relationship_name, relation_id=relation_id)
        relation.data[self.model.unit]["certificate"] = certificate  # type: ignore[union-attr]
        relation.data[self.model.unit]["private_key"] = private_key

    def _on_relation_joined(self, event):
        self.on.certificate_request.emit(relation_id=event.relation.id)


class CertControllerRequires(Object):

    on = CertControllerRequirerCharmEvents()

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
        logger.info(f"Raw relation data: {event.relation.data}")
        relation_data = event.relation.data
        certificate = relation_data[event.unit].get("certificate")
        private_key = relation_data[event.unit].get("private_key")
        if certificate and private_key:
            logger.info(f"Certificate available: {certificate}")
            self.on.certificate_available.emit(certificate=certificate, private_key=private_key)
