#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.


"""A placeholder charm for the Orc8r libs."""

from ops.charm import CharmBase
from ops.main import main


class Orc8rLibsCharm(CharmBase):
    """Placeholder charm for Orc8r libs."""

    pass


if __name__ == "__main__":
    main(Orc8rLibsCharm)
