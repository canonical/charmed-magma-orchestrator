#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest  # type: ignore

logger = logging.getLogger(__name__)
METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())

APPLICATION_NAME = "orc8r-ha"
CHARM_NAME = "magma-orc8r-ha"


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    charm = await ops_test.build_charm(".")
    resources = {
        f"{CHARM_NAME}-image": METADATA["resources"][f"{CHARM_NAME}-image"][
            "upstream-source"
        ],
    }
    await ops_test.model.deploy(
        charm, resources=resources, application_name=APPLICATION_NAME, trust=True
    )
    await ops_test.model.wait_for_idle(apps=[APPLICATION_NAME], status="active", timeout=1000)
