#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import os
from pathlib import Path
from typing import Optional

import pytest
import yaml

logger = logging.getLogger(__name__)
METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())

APPLICATION_NAME = "orc8r-bootstrapper"
CHARM_NAME = "magma-orc8r-bootstrapper"


class TestOrc8rBootstrapper:
    @staticmethod
    def _find_charm(charm_dir: str, charm_file_name: str) -> Optional[str]:
        for root, _, files in os.walk(charm_dir):
            for file in files:
                if file == charm_file_name:
                    return os.path.join(root, file)
        return None

    @staticmethod
    async def _deploy_postgresql(ops_test):
        await ops_test.model.deploy("postgresql-k8s", application_name="postgresql-k8s")

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

    @pytest.mark.abort_on_fail
    async def test_wait_for_blocked_status(self, ops_test, build_and_deploy):
        await ops_test.model.wait_for_idle(apps=[APPLICATION_NAME], status="blocked", timeout=1000)

    async def test_scale_up(self, ops_test, build_and_deploy):
        await ops_test.model.applications[APPLICATION_NAME].scale(2)

        await ops_test.model.wait_for_idle(
            apps=[APPLICATION_NAME], status="active", timeout=1000, wait_for_exact_units=2
        )

    @pytest.mark.xfail(reason="Bug in Juju: https://bugs.launchpad.net/juju/+bug/1977582")
    async def test_scale_down(self, ops_test, build_and_deploy):
        await ops_test.model.applications[APPLICATION_NAME].scale(1)

        await ops_test.model.wait_for_idle(
            apps=[APPLICATION_NAME], status="active", timeout=1000, wait_for_exact_units=1
        )
