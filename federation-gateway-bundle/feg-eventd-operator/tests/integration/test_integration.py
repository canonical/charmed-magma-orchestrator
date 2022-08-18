#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml

logger = logging.getLogger(__name__)
METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())

APPLICATION_NAME = "feg-eventd"
CHARM_NAME = "magma-feg-eventd"


class TestFegEapSim:
    @pytest.fixture(scope="module")
    @pytest.mark.abort_on_fail
    async def build_and_deploy(self, ops_test):
        charm = await ops_test.build_charm(".")
        resources = {
            f"{CHARM_NAME}-image": METADATA["resources"][f"{CHARM_NAME}-image"]["upstream-source"],
        }
        await ops_test.model.deploy(
            charm, resources=resources, application_name=APPLICATION_NAME, trust=True
        )

    async def test_wait_for_idle(self, ops_test, build_and_deploy):
        await ops_test.model.wait_for_idle(apps=[APPLICATION_NAME], status="active", timeout=1000)
