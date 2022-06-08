#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

from charms.magma_nms_magmalte.v0.admin_operator import AdminOperatorProvides
from ops.charm import CharmBase
from ops.main import main

logger = logging.getLogger(__name__)


class MagmaNmsMagmalteCharm(CharmBase):
    def __init__(self, *args):
        """Creates a new instance of this object for each event."""
        super().__init__(*args)

        self.admin_operator = AdminOperatorProvides(self, "magmalte")


if __name__ == "__main__":
    main(MagmaNmsMagmalteCharm)
