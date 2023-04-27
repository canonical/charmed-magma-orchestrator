#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import os
from pathlib import Path
from typing import Optional

import pytest
import yaml

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
CERTIFIER_METADATA = yaml.safe_load(Path("../orc8r-certifier-operator/metadata.yaml").read_text())
BOOTSTRAPPER_METADATA = yaml.safe_load(
    Path("../orc8r-bootstrapper-operator/metadata.yaml").read_text()
)
OBSIDIAN_METADATA = yaml.safe_load(Path("../orc8r-obsidian-operator/metadata.yaml").read_text())

DB_APPLICATION_NAME = "postgresql-k8s"
APPLICATION_NAME = "orc8r-nginx"
CHARM_NAME = "magma-orc8r-nginx"
CERTIFIER_APPLICATION_NAME = "orc8r-certifier"
CERTIFIER_CHARM_NAME = "magma-orc8r-certifier"
CERTIFIER_CHARM_FILE_NAME = "magma-orc8r-certifier_ubuntu-22.04-amd64.charm"
BOOTSTRAPPER_APPLICATION_NAME = "orc8r-bootstrapper"
BOOTSTRAPPER_CHARM_NAME = "magma-orc8r-bootstrapper"
BOOTSTRAPPER_CHARM_FILE_NAME = "magma-orc8r-bootstrapper_ubuntu-22.04-amd64.charm"
OBSIDIAN_APPLICATION_NAME = "orc8r-obsidian"
OBSIDIAN_CHARM_NAME = "magma-orc8r-obsidian"
OBSIDIAN_CHARM_FILE_NAME = "magma-orc8r-obsidian_ubuntu-22.04-amd64.charm"
DOMAIN = "example.com"


class TestOrc8rNginx:
    @pytest.fixture(scope="module")
    @pytest.mark.abort_on_fail
    async def setup(self, ops_test):
        await self._deploy_postgresql(ops_test)
        await self._deploy_tls_certificates_operator(ops_test)
        await self._deploy_orc8r_certifier(ops_test)
        await self._deploy_bootstrapper(ops_test)
        await self._deploy_orc8r_obsidian(ops_test)

    @staticmethod
    def _find_charm(charm_dir: str, charm_file_name: str) -> Optional[str]:
        for root, _, files in os.walk(charm_dir):
            for file in files:
                if file == charm_file_name:
                    return os.path.join(root, file)
        return None

    @staticmethod
    async def _deploy_postgresql(ops_test):
        await ops_test.model.deploy(
            DB_APPLICATION_NAME, application_name=DB_APPLICATION_NAME, channel="14/stable"
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
            config={"domain": DOMAIN},
            trust=True,
            series="jammy",
        )
        await ops_test.model.add_relation(
            relation1=CERTIFIER_APPLICATION_NAME, relation2=f"{DB_APPLICATION_NAME}:db"
        )
        await ops_test.model.add_relation(
            relation1=CERTIFIER_APPLICATION_NAME, relation2="tls-certificates-operator"
        )

    async def _deploy_bootstrapper(self, ops_test):
        bootstrapper_charm = self._find_charm(
            "../orc8r-bootstrapper-operator", BOOTSTRAPPER_CHARM_FILE_NAME
        )
        if not bootstrapper_charm:
            bootstrapper_charm = await ops_test.build_charm("../orc8r-bootstrapper-operator/")
        resources = {
            f"{BOOTSTRAPPER_CHARM_NAME}-image": BOOTSTRAPPER_METADATA["resources"][
                f"{BOOTSTRAPPER_CHARM_NAME}-image"
            ]["upstream-source"],
        }
        await ops_test.model.deploy(
            bootstrapper_charm,
            resources=resources,
            application_name=BOOTSTRAPPER_APPLICATION_NAME,
            trust=True,
            series="jammy",
        )
        await ops_test.model.add_relation(
            relation1=BOOTSTRAPPER_APPLICATION_NAME, relation2=f"{DB_APPLICATION_NAME}:database"
        )
        await ops_test.model.add_relation(
            relation1=BOOTSTRAPPER_APPLICATION_NAME, relation2="orc8r-certifier:cert-root-ca"
        )

    async def _deploy_orc8r_obsidian(self, ops_test):
        obsidian_charm = self._find_charm("../orc8r-obsidian-operator", OBSIDIAN_CHARM_FILE_NAME)
        if not obsidian_charm:
            obsidian_charm = await ops_test.build_charm("../orc8r-obsidian-operator/")
        resources = {
            f"{OBSIDIAN_CHARM_NAME}-image": OBSIDIAN_METADATA["resources"][
                f"{OBSIDIAN_CHARM_NAME}-image"
            ]["upstream-source"],
        }
        await ops_test.model.deploy(
            obsidian_charm,
            resources=resources,
            application_name=OBSIDIAN_APPLICATION_NAME,
            trust=True,
            series="jammy",
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
            trust=True,
            config={"domain": DOMAIN},
            series="jammy",
        )

    @pytest.mark.abort_on_fail
    async def test_wait_for_blocked_status(self, ops_test, build_and_deploy):
        await ops_test.model.wait_for_idle(apps=[APPLICATION_NAME], status="blocked", timeout=1000)

    async def test_relate_and_wait_for_idle(self, ops_test, build_and_deploy):
        await ops_test.model.add_relation(
            relation1=f"{APPLICATION_NAME}:cert-controller",
            relation2="orc8r-certifier:cert-controller",
        )
        await ops_test.model.add_relation(
            relation1=f"{APPLICATION_NAME}:cert-certifier",
            relation2="orc8r-certifier:cert-certifier",
        )
        await ops_test.model.add_relation(
            relation1=f"{APPLICATION_NAME}:cert-root-ca",
            relation2="orc8r-certifier:cert-root-ca",
        )
        await ops_test.model.add_relation(
            relation1=f"{APPLICATION_NAME}:magma-orc8r-bootstrapper",
            relation2="orc8r-bootstrapper:magma-orc8r-bootstrapper",
        )
        await ops_test.model.add_relation(
            relation1=f"{APPLICATION_NAME}:magma-orc8r-obsidian",
            relation2="orc8r-obsidian:magma-orc8r-obsidian",
        )
        await ops_test.model.wait_for_idle(apps=[APPLICATION_NAME], status="active", timeout=1000)

    async def test_scale_up(self, ops_test, setup, build_and_deploy):
        await ops_test.model.applications[APPLICATION_NAME].scale(2)

        await ops_test.model.wait_for_idle(
            apps=[APPLICATION_NAME], status="active", timeout=1000, wait_for_exact_units=2
        )

    @pytest.mark.xfail(reason="Bug in Juju: https://bugs.launchpad.net/juju/+bug/1977582")
    async def test_scale_down(self, ops_test, setup, build_and_deploy):
        await ops_test.model.applications[APPLICATION_NAME].scale(1)

        await ops_test.model.wait_for_idle(
            apps=[APPLICATION_NAME], status="active", timeout=60, wait_for_exact_units=1
        )
