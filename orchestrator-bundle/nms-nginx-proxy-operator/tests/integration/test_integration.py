#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import os
from pathlib import Path
from typing import Optional

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
CERTIFIER_CHARM_FILE_NAME = "magma-orc8r-certifier_ubuntu-20.04-amd64.charm"
NMS_MAGMALTE_APPLICATION_NAME = "nms-magmalte"
NMS_MAGMALTE_CHARM_NAME = "magma-nms-magmalte"
NMS_MAGMALTE_CHARM_FILE_NAME = "magma-nms-magmalte_ubuntu-20.04-amd64.charm"


class TestNmsNginxProxy:
    @pytest.fixture(scope="module")
    @pytest.mark.abort_on_fail
    async def setup(self, ops_test):
        await self._deploy_postgresql(ops_test)
        await self._deploy_tls_certificates_operator(ops_test)
        await self._deploy_orc8r_certifier(ops_test)
        await self._deploy_nms_magmalte(ops_test)

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

    @staticmethod
    async def _deploy_tls_certificates_operator(ops_test):
        await ops_test.model.deploy(
            "tls-certificates-operator",
            application_name="tls-certificates-operator",
            config={"generate-self-signed-certificates": True},
            channel="edge",
        )

    async def _deploy_orc8r_certifier(self, ops_test):
        certifier_charm = self._find_charm(
            "../orc8r-certifier-operator", CERTIFIER_CHARM_FILE_NAME
        )
        if not certifier_charm:
            certifier_charm = await ops_test.build_charm("../orc8r-certifier-operator/")
        resources = {
            f"{CERTIFIER_CHARM_NAME}-image": CERTIFIER_METADATA["resources"][
                f"{CERTIFIER_CHARM_NAME}-image"
            ]["upstream-source"],
        }
        await ops_test.model.deploy(
            certifier_charm,
            resources=resources,
            application_name=CERTIFIER_APPLICATION_NAME,
            config={"domain": "example.com"},
            trust=True,
        )
        await ops_test.model.add_relation(
            relation1=CERTIFIER_APPLICATION_NAME, relation2="postgresql-k8s:db"
        )
        await ops_test.model.add_relation(
            relation1=CERTIFIER_APPLICATION_NAME, relation2="tls-certificates-operator"
        )

    async def _deploy_nms_magmalte(self, ops_test):
        magmalte_charm = self._find_charm("../nms-magmalte-operator", NMS_MAGMALTE_CHARM_FILE_NAME)
        if not magmalte_charm:
            magmalte_charm = await ops_test.build_charm("../nms-magmalte-operator/")
        resources = {
            f"{NMS_MAGMALTE_CHARM_NAME}-image": NMS_MAGMALTE_METADATA["resources"][
                f"{NMS_MAGMALTE_CHARM_NAME}-image"
            ]["upstream-source"],
        }
        await ops_test.model.deploy(
            magmalte_charm,
            resources=resources,
            application_name=NMS_MAGMALTE_APPLICATION_NAME,
            trust=True,
        )
        await ops_test.model.add_relation(
            relation1=NMS_MAGMALTE_APPLICATION_NAME, relation2="postgresql-k8s:db"
        )
        await ops_test.model.add_relation(
            relation1=NMS_MAGMALTE_APPLICATION_NAME,
            relation2="orc8r-certifier:cert-admin-operator",
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
            relation1=APPLICATION_NAME, relation2="orc8r-certifier:cert-controller"
        )
        await ops_test.model.add_relation(
            relation1=APPLICATION_NAME, relation2="nms-magmalte:magma-nms-magmalte"
        )
        await ops_test.model.wait_for_idle(apps=[APPLICATION_NAME], status="active", timeout=1000)
