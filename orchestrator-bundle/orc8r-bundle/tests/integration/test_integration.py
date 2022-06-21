#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
from pytest_operator.plugin import OpsTest  # type: ignore[import]  # noqa: F401

logger = logging.getLogger(__name__)


class TestOrc8rBundle:
    @pytest.fixture(scope="module")
    @pytest.mark.abort_on_fail
    async def deploy_bundle(self, ops_test):
        pass
    
    async def test_relate_and_wait_for_idle(self, ops_test, deploy_bundle):
        await ops_test.model.wait_for_idle(status="active", timeout=1000)
