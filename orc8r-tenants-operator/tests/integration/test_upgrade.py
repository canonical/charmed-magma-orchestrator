#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import pytest
import yaml

logger = logging.getLogger(__name__)
METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())

APPLICATION_NAME = "orc8r-tenants"
CHARM_NAME = "magma-orc8r-tenants"
CHARM_RESOURCES = {
    f"{CHARM_NAME}-image": METADATA["resources"][f"{CHARM_NAME}-image"]["upstream-source"],
}


class TestOrc8rTenants:
    @pytest.fixture(scope="module")
    @pytest.mark.abort_on_fail
    async def setup(self, ops_test):
        await self._deploy_postgresql(ops_test)
        await self._deploy_orc8r_tenants_from_latest_stable_channel(ops_test)
        await self._relate_orc8r_tenants_and_postgresql(ops_test)
        await ops_test.model.wait_for_idle(apps=[APPLICATION_NAME], status="active", timeout=600)

    @pytest.mark.abort_on_fail
    async def test_workload_container_image_comes_from_charmhub(self, ops_test, setup):
        image = await self._get_container_image(ops_test, APPLICATION_NAME)
        assert "registry.jujucharms.com" in image

    @pytest.fixture(scope="module")
    @pytest.mark.abort_on_fail
    async def build_and_refresh(self, ops_test, setup):
        charm = await ops_test.build_charm(".")

        await ops_test.model.applications[APPLICATION_NAME].refresh(
            path=charm, resources=CHARM_RESOURCES
        )

    @pytest.mark.abort_on_fail
    async def test_wait_for_active_idle_after_refresh(self, ops_test, setup, build_and_refresh):
        await ops_test.model.wait_for_idle(apps=[APPLICATION_NAME], status="active", timeout=180)

    @pytest.mark.abort_on_fail
    async def test_workload_container_image_updated_with_metadata_oci_image(
        self, ops_test, setup, build_and_refresh
    ):
        image = await self._get_container_image(ops_test, APPLICATION_NAME)
        assert image == CHARM_RESOURCES[f"{CHARM_NAME}-image"]

    @staticmethod
    async def _deploy_postgresql(ops_test):
        await ops_test.model.deploy("postgresql-k8s", application_name="postgresql-k8s")

    @staticmethod
    async def _deploy_orc8r_tenants_from_latest_stable_channel(ops_test):
        await ops_test.model.deploy(
            "magma-orc8r-tenants",
            application_name="orc8r-tenants",
            channel="latest/stable",
            trust=True,
        )

    @staticmethod
    async def _relate_orc8r_tenants_and_postgresql(ops_test):
        await ops_test.model.add_relation(
            relation1=APPLICATION_NAME, relation2="postgresql-k8s:db"
        )

    @staticmethod
    async def _get_container_image(ops_test, app_name):
        cmd = [
            "sg",
            "microk8s",
            "-c",
            " ".join(
                [
                    "microk8s.kubectl",
                    "get",
                    "pods",
                    "-n",
                    ops_test.model_name,
                    "-o",
                    "jsonpath='{.items[*].spec.containers[1].image}'",
                    "-l",
                    f"app.kubernetes.io/name={app_name}",
                ]
            )
        ]
        _, image, __ = await ops_test.run(*cmd)
        return image
