"""

## Getting started

```shell
charmcraft fetch-lib charms.magma_nms_magmalte.v0.admin_operator
```

### Requirer Charm

```python
class AdminOperatorRequires(Object):

    on = AdminOperatorRequirerCharmEvents()

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


import logging

from ops.charm import CharmEvents
from ops.framework import EventBase, EventSource, Object


# The unique Charmhub library identifier, never change it
LIBID = "02c2b79320ac460eb4309a9c3fbd4605"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 6

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
    def __init__(self, handle, certificate: str):
        super().__init__(handle)
        self.certificate = certificate

    def snapshot(self):
        return {
            "certificate": self.certificate,
        }

    def restore(self, snapshot):
        self.certificate = snapshot["certificate"]


class AdminOperatorProviderCharmEvents(CharmEvents):
    certificate_request = EventSource(CertificateRequestEvent)


class AdminOperatorRequirerCharmEvents(CharmEvents):
    certificate_available = EventSource(CertificateAvailableEvent)


class AdminOperatorProvides(Object):

    on = AdminOperatorProviderCharmEvents()

    def __init__(self, charm, relationship_name: str):
        self.relationship_name = relationship_name
        self.charm = charm
        super().__init__(charm, relationship_name)
        self.framework.observe(
            charm.on[relationship_name].relation_joined, self._on_relation_joined
        )
        self.certificate = None

    def set_certificate(self, certificate: str, relation_id: int):
        relation = self.model.get_relation(
            relation_name=self.relationship_name, relation_id=relation_id)
        relation.data[self.model.unit]["certificate"] = certificate  # type: ignore[union-attr]

    def _on_relation_joined(self, event):
        self.on.certificate_request.emit(relation_id=event.relation.id)


class AdminOperatorRequires(Object):

    on = AdminOperatorRequirerCharmEvents()

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
        if certificate:
            logger.info(f"Certificate available: {certificate}")
            self.on.certificate_available.emit(certificate=certificate)
