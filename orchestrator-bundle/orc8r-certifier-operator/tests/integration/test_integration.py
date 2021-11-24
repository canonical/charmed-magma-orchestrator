#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest  # type: ignore[import]  # noqa: F401

logger = logging.getLogger(__name__)
METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())

APPLICATION_NAME = "orc8r-certifier"
CHARM_NAME = "magma-orc8r-certifier"


class TestOrc8rCertifier:
    @pytest.fixture(scope="module")
    async def setup(self, ops_test):
        await ops_test.model.deploy("postgresql-k8s", application_name="postgresql-k8s")
        await ops_test.model.wait_for_idle(apps=["postgresql-k8s"], status="active", timeout=1000)

    @pytest.mark.abort_on_fail
    async def test_build_and_deploy(self, ops_test, setup):
        charm = await ops_test.build_charm(".")
        resources = {
            f"{CHARM_NAME}-image": METADATA["resources"][f"{CHARM_NAME}-image"]["upstream-source"],
        }
        await ops_test.model.deploy(
            charm,
            resources=resources,
            application_name=APPLICATION_NAME,
            config={"domain": "example.com"},
            trust=True,
        )
        await ops_test.model.add_relation(
            relation1=APPLICATION_NAME, relation2="postgresql-k8s:db"
        )
        await ops_test.model.wait_for_idle(apps=[APPLICATION_NAME], status="active", timeout=1000)
