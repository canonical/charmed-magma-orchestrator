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
CERTIFIER_METADATA = yaml.safe_load(Path("../orc8r-certifier-operator/metadata.yaml").read_text())
NMS_MAGMALTE_METADATA = yaml.safe_load(Path("../nms-magmalte-operator/metadata.yaml").read_text())

APPLICATION_NAME = "nms-nginx-proxy"
CHARM_NAME = "magma-nms-nginx-proxy"
CERTIFIER_APPLICATION_NAME = "orc8r-certifier"
CERTIFIER_CHARM_NAME = "magma-orc8r-certifier"
NMS_MAGMALTE_APPLICATION_NAME = "nms-magmalte"
NMS_MAGMALTE_CHARM_NAME = "magma-nms-magmalte"


class TestNmsNginxProxy:
    @pytest.fixture(scope="module")
    @pytest.mark.abort_on_fail
    async def setup(self, ops_test):
        await self._deploy_postgresql(ops_test)
        await self._deploy_orc8r_certifier(ops_test)
        await self._deploy_nms_magmalte(ops_test)


    @staticmethod
    async def _deploy_postgresql(ops_test):
        await ops_test.model.deploy("postgresql-k8s", application_name="postgresql-k8s")
        await ops_test.model.wait_for_idle(apps=["postgresql-k8s"], status="active", timeout=1000)

    @staticmethod
    async def _deploy_orc8r_certifier(ops_test):
        charm = await ops_test.build_charm("../orc8r-certifier-operator/")
        resources = {
            f"{CERTIFIER_CHARM_NAME}-image": CERTIFIER_METADATA["resources"][
                f"{CERTIFIER_CHARM_NAME}-image"
            ]["upstream-source"],
        }
        await ops_test.model.deploy(
            charm,
            resources=resources,
            application_name=CERTIFIER_APPLICATION_NAME,
            config={"domain": "example.com"},
            trust=True,
        )
        await ops_test.model.wait_for_idle(
            apps=[CERTIFIER_APPLICATION_NAME], status="blocked", timeout=1000
        )
        await ops_test.model.add_relation(
            relation1=CERTIFIER_APPLICATION_NAME, relation2="postgresql-k8s:db"
        )
        await ops_test.model.wait_for_idle(
            apps=[CERTIFIER_APPLICATION_NAME], status="active", timeout=1000
        )
        

    @staticmethod
    async def _deploy_nms_magmalte(ops_test):
        charm = await ops_test.build_charm("../nms-magmalte-operator/")
        resources = {
            f"{NMS_MAGMALTE_CHARM_NAME}-image": NMS_MAGMALTE_METADATA["resources"][
                f"{NMS_MAGMALTE_CHARM_NAME}-image"
            ]["upstream-source"],
        }
        await ops_test.model.deploy(
            charm, resources=resources, application_name=NMS_MAGMALTE_APPLICATION_NAME, trust=True
        )
        await ops_test.model.wait_for_idle(
            apps=[NMS_MAGMALTE_APPLICATION_NAME], status="blocked", timeout=1000
        )
        await ops_test.model.add_relation(
            relation1=NMS_MAGMALTE_APPLICATION_NAME, relation2="postgresql-k8s:db"
        )
        await ops_test.model.add_relation(
            relation1=NMS_MAGMALTE_APPLICATION_NAME, relation2="orc8r-certifier:certifier"
        )
        await ops_test.model.wait_for_idle(
            apps=[NMS_MAGMALTE_APPLICATION_NAME], status="active", timeout=1000
        )
        
    @pytest.fixture(scope="module")
    @pytest.mark.abort_on_fail
    async def build_and_deploy_charm(self, ops_test, setup):
        charm = await ops_test.build_charm(".")
        resources = {
            f"{CHARM_NAME}-image": METADATA["resources"][f"{CHARM_NAME}-image"]["upstream-source"],
        }
        await ops_test.model.deploy(
            charm, resources=resources, application_name=APPLICATION_NAME, trust=True
        )
    
    @pytest.mark.abort_on_fail
    async def test_wait_for_blocked_status(self, ops_test, build_and_deploy_charm):
        await ops_test.model.wait_for_idle(apps=[APPLICATION_NAME], status="blocked", timeout=1000)

    async def test_relate_and_wait_for_idle(self, ops_test, setup, build_and_deploy_charm):
        await ops_test.model.add_relation(
            relation1=APPLICATION_NAME, relation2="orc8r-certifier:certifier"
        )
        await ops_test.model.add_relation(
            relation1=APPLICATION_NAME, relation2="nms-magmalte:magmalte"
        )
        await ops_test.model.wait_for_idle(apps=[APPLICATION_NAME], status="active", timeout=1000)