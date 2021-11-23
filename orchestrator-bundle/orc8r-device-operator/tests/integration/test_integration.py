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

APPLICATION_NAME = "magma-orc8r-device"


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    charm = await ops_test.build_charm(".")
    resources = {
        f"{APPLICATION_NAME}-image": METADATA["resources"][f"{APPLICATION_NAME}-image"][
            "upstream-source"
        ],
    }
    await ops_test.model.deploy("postgresql-k8s", application_name="postgresql-k8s")
    await ops_test.model.deploy(
        charm, resources=resources, application_name=APPLICATION_NAME, trust=True
    )
    await ops_test.model.add_relation(relation1=APPLICATION_NAME, relation2="postgresql-k8s:db")
    await ops_test.model.wait_for_idle(
        apps=["postgresql-k8s", APPLICATION_NAME], status="active", timeout=1000
    )
