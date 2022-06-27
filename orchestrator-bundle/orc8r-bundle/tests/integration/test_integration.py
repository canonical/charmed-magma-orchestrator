#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
from pytest_operator.plugin import OpsTest  # type: ignore[import]  # noqa: F401

from helpers import (cli_deploy_bundle)


logger = logging.getLogger(__name__)


class TestOrc8rBundle:
    @pytest.fixture(scope="module")
    @pytest.mark.abort_on_fail
    async def deploy_bundle(self, ops_test: OpsTest):
        run_args = [
            "juju",
            "deploy",
            "/home/ubuntu/charmed-magma/orchestrator-bundle/bundle-local.yaml",
            "--trust",
        ]

        logger.info("Deploying bundle")
        retcode, stdout, stderr = await ops_test.run(*run_args)
        logger.info(stdout)

    async def test_wait_for_idle(self, ops_test: OpsTest, deploy_bundle):
        await ops_test.model.wait_for_idle(status="active", timeout=1500)