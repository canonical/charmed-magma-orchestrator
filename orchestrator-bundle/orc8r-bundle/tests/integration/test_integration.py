#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
from pytest_operator.plugin import OpsTest  # type: ignore[import]  # noqa: F401

from juju.controller import Controller


logger = logging.getLogger(__name__)


class TestOrc8rBundle:
    async def cli_deploy_bundle(ops_test: OpsTest, name: str, channel: str = "edge"):
        run_args = [
            "juju",
            "deploy",
            "./bundle-local.yaml",
            "--trust",
            "-m",
            ops_test.model_full_name,
        ]

        retcode, stdout, stderr = await ops_test.run(*run_args)
        logger.info("Deploying bundle")
        logger.info(stdout)

    @pytest.fixture(scope="module")
    @pytest.mark.abort_on_fail
    async def deploy_bundle(self, ops_test: OpsTest):
        logger.info("Deploying bundle")
        await cli_deploy_bundle(ops_test, "magma-orc8r")
        logger.info("Bundle deployed!")
        
    
    async def test_wait_for_idle(self, ops_test: OpsTest, deploy_bundle):
        await ops_test.model.wait_for_idle(status="active", timeout=1500)
