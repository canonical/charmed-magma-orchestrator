#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from pathlib import Path

import integration_test_utils as integration_utils  # type: ignore[import]
import pytest
import yaml

logger = logging.getLogger(__name__)
METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())

APPLICATION_NAME = "nms-magmalte"
CHARM_NAME = "magma-nms-magmalte"


class TestNmsMagmaLTE:
    @pytest.fixture(scope="module")
    @pytest.mark.abort_on_fail
    async def setup(self, ops_test):
        await integration_utils.deploy_postgresql(ops_test, channel="14/stable")
        await integration_utils.deploy_tls_certificates_operator(ops_test, channel="edge")
        await integration_utils.deploy_orc8r_certifier(ops_test)
        await integration_utils.deploy_grafana_k8s_operator(ops_test, channel="edge")
        await integration_utils.deploy_prometheus_k8s_operator(ops_test, channel="edge")

    @pytest.fixture(scope="module")
    @pytest.mark.abort_on_fail
    async def build_and_deploy_charm(self, ops_test):
        charm = await ops_test.build_charm(".")
        resources = {
            f"{CHARM_NAME}-image": METADATA["resources"][f"{CHARM_NAME}-image"]["upstream-source"],
        }
        await ops_test.model.deploy(
            charm,
            resources=resources,
            application_name=APPLICATION_NAME,
            trust=True,
            series="jammy",
        )

    async def test_wait_for_blocked_status(self, ops_test, setup, build_and_deploy_charm):
        await ops_test.model.wait_for_idle(apps=[APPLICATION_NAME], status="blocked", timeout=1000)

    async def test_relate_and_wait_for_idle(self, ops_test, setup, build_and_deploy_charm):
        await ops_test.model.add_relation(
            relation1=APPLICATION_NAME, relation2="postgresql-k8s:database"
        )
        await ops_test.model.add_relation(
            relation1=APPLICATION_NAME,
            relation2="orc8r-certifier:cert-admin-operator",
        )
        await ops_test.model.add_relation(
            relation1=f"{APPLICATION_NAME}:grafana-auth",
            relation2="grafana-k8s",
        )
        await ops_test.model.wait_for_idle(apps=[APPLICATION_NAME], status="active", timeout=1000)

    async def test_scale_up(self, ops_test, setup, build_and_deploy_charm):
        await ops_test.model.applications[APPLICATION_NAME].scale(2)

        await ops_test.model.wait_for_idle(
            apps=[APPLICATION_NAME], status="active", timeout=1000, wait_for_exact_units=2
        )

    @pytest.mark.xfail(reason="Bug in Juju: https://bugs.launchpad.net/juju/+bug/1977582")
    async def test_scale_down(self, ops_test, setup, build_and_deploy_charm):
        await ops_test.model.applications[APPLICATION_NAME].scale(1)

        await ops_test.model.wait_for_idle(
            apps=[APPLICATION_NAME], status="active", timeout=60, wait_for_exact_units=1
        )

    @pytest.mark.xfail(reason="Postgres bug https://warthogs.atlassian.net/browse/DPE-1470")
    async def test_remove_db_application(self, ops_test, setup, build_and_deploy_charm):
        await integration_utils.remove_postgresql(ops_test)
        await ops_test.model.wait_for_idle(apps=[APPLICATION_NAME], status="blocked", timeout=60)

    @pytest.mark.xfail(reason="Postgres bug https://warthogs.atlassian.net/browse/DPE-1470")
    async def test_redeploy_db(self, ops_test, setup, build_and_deploy_charm):
        await integration_utils.redeploy_and_relate_postgresql(ops_test)
        await ops_test.model.wait_for_idle(apps=[APPLICATION_NAME], status="active", timeout=60)
