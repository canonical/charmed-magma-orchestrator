# Copyright 2020 Canonical Ltd.
# See LICENSE file for licensing details.

import ops.framework
import ops.model


class ClientRelations(ops.framework.Object):
    def __init__(self, charm: ops.charm.CharmBase, key: str):
        super().__init__(charm, key)
        self.unit = self.model.unit
        self.framework.observe(charm.on["certifier"].relation_changed, self._on_relation_changed)

    def _on_relation_changed(self, event: ops.charm.RelationEvent):
        """Adds the domain field to relation's data bucket so that it can be used by the client.
        To access data bucket, client should implement callback for on_relation_changed event.
        To learn more about getting relation data, visit
        [Juju docs](https://juju.is/docs/sdk/relations#heading--relation-data).
        """
        domain = self.model.config["domain"]

        to_publish = [event.relation.data[self.unit]]
        for bucket in to_publish:
            bucket["domain"] = domain
