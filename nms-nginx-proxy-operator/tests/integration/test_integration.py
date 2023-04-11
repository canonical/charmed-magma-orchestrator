#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

from pathlib import Path

import integration_test_utils as integration_utils  # type: ignore[import]
import pytest
import yaml

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
CERTIFIER_METADATA = yaml.safe_load(Path("../orc8r-certifier-operator/metadata.yaml").read_text())
NMS_MAGMALTE_METADATA = yaml.safe_load(Path("../nms-magmalte-operator/metadata.yaml").read_text())

APPLICATION_NAME = "nms-nginx-proxy"
CHARM_NAME = "magma-nms-nginx-proxy"


class TestNmsNginxProxy:
    @pytest.fixture(scope="module")
    @pytest.mark.abort_on_fail
    async def setup(self, ops_test):
        await integration_utils.deploy_postgresql(ops_test)
        await integration_utils.deploy_tls_certificates_operator(ops_test)
        await integration_utils.deploy_orc8r_certifier(ops_test)
        await integration_utils.deploy_grafana_k8s_operator(ops_test)
        await integration_utils.deploy_prometheus_k8s_operator(ops_test)
        await integration_utils.deploy_nms_magmalte(ops_test)

    @pytest.fixture(scope="module")
    @pytest.mark.abort_on_fail
    async def build_and_deploy_charm(self, ops_test, setup):
        charm = await ops_test.build_charm(".")
        integration_utils.deploy_tested_charm(APPLICATION_NAME)
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
