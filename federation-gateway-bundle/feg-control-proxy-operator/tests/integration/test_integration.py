#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml

logger = logging.getLogger(__name__)
METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
CONFIG_CERTIFICATES = yaml.safe_load(Path("./certs-config.yaml").read_text())

APPLICATION_NAME = "feg-control-proxy"
CHARM_NAME = "magma-feg-control-proxy"


class TestFegControlProxy:
    @pytest.fixture(scope="module")
    @pytest.mark.abort_on_fail
    async def build_and_deploy(self, ops_test):
        charm = await ops_test.build_charm(".")
        resources = {
            f"{CHARM_NAME}-image": METADATA["resources"][f"{CHARM_NAME}-image"]["upstream-source"],
        }
        config_certificates = {
            "controller-key": CONFIG_CERTIFICATES["feg-control-proxy"]["controller-key"],
            "controller-crt": CONFIG_CERTIFICATES["feg-control-proxy"]["controller-crt"],
            "root-ca-pem": CONFIG_CERTIFICATES["feg-control-proxy"]["root-ca-pem"],
            "root-ca-key": CONFIG_CERTIFICATES["feg-control-proxy"]["root-ca-key"],
        }

        await ops_test.model.deploy(
            charm,
            resources=resources,
            application_name=APPLICATION_NAME,
            config=config_certificates,
            trust=True,
        )

    async def test_wait_for_idle(self, ops_test, build_and_deploy):
        await ops_test.model.wait_for_idle(apps=[APPLICATION_NAME], status="active", timeout=1000)
