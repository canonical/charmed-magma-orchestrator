#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml

logger = logging.getLogger(__name__)
METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())

APPLICATION_NAME = "orc8r-certifier"
CHARM_NAME = "magma-orc8r-certifier"
DOMAIN = "whatever.com"
DB_APPLICATION_NAME = "postgresql-k8s"


class TestOrc8rCertifier:
    @pytest.fixture(scope="module")
    @pytest.mark.abort_on_fail
    async def setup(self, ops_test):
        await self._deploy_postgresql(ops_test)
        await self._deploy_tls_certificates_operator(ops_test)

    @staticmethod
    async def _deploy_postgresql(ops_test):
        await ops_test.model.deploy(
            DB_APPLICATION_NAME,
            application_name=DB_APPLICATION_NAME,
            channel="14/stable",
        )

    @staticmethod
    async def _deploy_tls_certificates_operator(ops_test):
        await ops_test.model.deploy(
            "tls-certificates-operator",
            application_name="tls-certificates-operator",
            config={
                "generate-self-signed-certificates": True,
                "ca-common-name": f"rootca.{DOMAIN}",
            },
            channel="edge",
        )

    @pytest.fixture(scope="module")
    @pytest.mark.abort_on_fail
    async def build_and_deploy(self, ops_test, setup):
        charm = await ops_test.build_charm(".")
        resources = {
            f"{CHARM_NAME}-image": METADATA["resources"][f"{CHARM_NAME}-image"]["upstream-source"],
        }
        await ops_test.model.deploy(
            charm,
            resources=resources,
            application_name=APPLICATION_NAME,
            config={"domain": DOMAIN},
            trust=True,
            series="jammy",
        )

    @pytest.mark.abort_on_fail
    async def test_wait_for_blocked_status(self, ops_test, setup, build_and_deploy):
        await ops_test.model.wait_for_idle(apps=[APPLICATION_NAME], status="blocked", timeout=1000)

    async def test_build_and_deploy(self, ops_test, setup, build_and_deploy):
        await ops_test.model.add_relation(
            relation1=APPLICATION_NAME, relation2=f"{DB_APPLICATION_NAME}:database"
        )
        await ops_test.model.add_relation(
            relation1=APPLICATION_NAME, relation2="tls-certificates-operator"
        )
        await ops_test.model.wait_for_idle(apps=[APPLICATION_NAME], status="active", timeout=1000)

    @pytest.mark.xfail(reason="https://warthogs.atlassian.net/browse/DPE-1470")
    async def test_remove_db_application(self, ops_test, setup, build_and_deploy):
        await ops_test.model.remove_application(
            DB_APPLICATION_NAME, block_until_done=True, force=True
        )
        await ops_test.model.wait_for_idle(apps=[APPLICATION_NAME], status="blocked", timeout=1000)

    @pytest.mark.xfail(reason="https://warthogs.atlassian.net/browse/DPE-1470")
    async def test_redeploy_db(self, ops_test, setup, build_and_deploy):
        await self._deploy_postgresql(ops_test)
        await ops_test.model.add_relation(
            relation1=APPLICATION_NAME, relation2=f"{DB_APPLICATION_NAME}:database"
        )
        await ops_test.model.wait_for_idle(apps=[APPLICATION_NAME], status="active", timeout=1000)

    async def test_build_and_deploy_and_scale_up(self, ops_test, setup, build_and_deploy):
        await ops_test.model.applications[APPLICATION_NAME].scale(2)

        await ops_test.model.wait_for_idle(
            apps=[APPLICATION_NAME], status="active", timeout=1000, wait_for_exact_units=2
        )

    @pytest.mark.xfail(reason="Bug in Juju: https://bugs.launchpad.net/juju/+bug/1977582")
    async def test_build_and_deploy_and_scale_down(self, ops_test, setup, build_and_deploy):
        await ops_test.model.applications[APPLICATION_NAME].scale(1)

        await ops_test.model.wait_for_idle(
            apps=[APPLICATION_NAME], status="active", timeout=60, wait_for_exact_units=1
        )
