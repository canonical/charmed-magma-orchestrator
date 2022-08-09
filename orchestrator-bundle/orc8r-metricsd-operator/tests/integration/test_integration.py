#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import os
from pathlib import Path
from typing import Union

import pytest
import yaml
from pytest_operator.plugin import OpsTest  # type: ignore[import]  # noqa: F401

logger = logging.getLogger(__name__)
METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())

APPLICATION_NAME = "orc8r-metricsd"
CHARM_NAME = "magma-orc8r-metricsd"
CERTIFIER_APPLICATION_NAME = "orc8r-certifier"
ORCHESTRATOR_APPLICATION_NAME = "orc8r-orchestrator"
ACCESSD_APPLICATION_NAME = "orc8r-accessd"
SERVICE_REGISTRY_APPLICATION_NAME = "orc8r-service-registry"


class TestOrc8rMetricsd:
    @pytest.fixture(scope="module")
    @pytest.mark.abort_on_fail
    async def setup(self, ops_test):
        await ops_test.model.set_config({"update-status-hook-interval": "2s"})
        await self._deploy_postgresql(ops_test)
        await self._deploy_alertmanager(ops_test)
        await self._deploy_prometheus(ops_test)
        await self._deploy_prometheus_configurer(ops_test)
        await self._deploy_tls_certificates_operator(ops_test)
        await self._deploy_orc8r_service_registry(ops_test)
        await self._deploy_orc8r_certifier(ops_test)
        await self._deploy_prometheus_cache(ops_test)
        await self._deploy_orc8r_accessd(ops_test)
        await self._deploy_orc8r_orchestrator(ops_test)

    @staticmethod
    def _find_charm(charm_dir: str, charm_file_name: str) -> Union[str, None]:
        for root, _, files in os.walk(charm_dir):
            for file in files:
                if file == charm_file_name:
                    return os.path.join(root, file)
        return None

    @staticmethod
    async def _deploy_postgresql(ops_test):
        await ops_test.model.deploy("postgresql-k8s", application_name="postgresql-k8s")

    @staticmethod
    async def _deploy_alertmanager(ops_test):
        await ops_test.model.deploy(
            "alertmanager-k8s",
            application_name="orc8r-alertmanager",
            channel="edge",
        )

    @staticmethod
    async def _deploy_prometheus(ops_test):
        await ops_test.model.deploy(
            "prometheus-k8s",
            application_name="orc8r-prometheus",
            channel="edge",
        )

    @staticmethod
    async def _deploy_prometheus_configurer(ops_test):
        await ops_test.model.deploy(
            "prometheus-configurer-k8s",
            application_name="orc8r-prometheus-configurer",
            channel="edge",
        )
        await ops_test.model.add_relation(
            relation1="orc8r-prometheus-configurer",
            relation2="orc8r-prometheus:receive-remote-write",
        )

    @staticmethod
    async def _deploy_tls_certificates_operator(ops_test):
        await ops_test.model.deploy(
            "tls-certificates-operator",
            application_name="tls-certificates-operator",
            config={"generate-self-signed-certificates": True},
            channel="edge",
        )

    @staticmethod
    async def _deploy_orc8r_service_registry(ops_test):
        await ops_test.model.deploy(
            "magma-orc8r-service-registry",
            application_name=SERVICE_REGISTRY_APPLICATION_NAME,
            channel="edge",
        )

    @staticmethod
    async def _deploy_orc8r_certifier(ops_test):
        await ops_test.model.deploy(
            "magma-orc8r-certifier",
            application_name=CERTIFIER_APPLICATION_NAME,
            config={"domain": "example.com"},
            channel="edge",
        )
        await ops_test.model.add_relation(
            relation1=CERTIFIER_APPLICATION_NAME, relation2="postgresql-k8s:db"
        )
        await ops_test.model.add_relation(
            relation1=CERTIFIER_APPLICATION_NAME, relation2="tls-certificates-operator"
        )
        await ops_test.model.wait_for_idle(
            apps=[CERTIFIER_APPLICATION_NAME], status="active", timeout=1000
        )

    @staticmethod
    async def _deploy_prometheus_cache(ops_test):
        await ops_test.model.deploy(
            "prometheus-edge-hub",
            application_name="orc8r-prometheus-cache",
            channel="edge",
            trust=True,
        )

    @staticmethod
    async def _deploy_orc8r_accessd(ops_test):
        await ops_test.model.deploy(
            "magma-orc8r-accessd",
            application_name=ACCESSD_APPLICATION_NAME,
            channel="edge",
            trust=True,
        )
        await ops_test.model.add_relation(
            relation1=ACCESSD_APPLICATION_NAME, relation2="postgresql-k8s:db"
        )
        await ops_test.model.wait_for_idle(
            apps=[ACCESSD_APPLICATION_NAME], status="active", timeout=1000
        )

    @staticmethod
    async def _deploy_orc8r_orchestrator(ops_test):
        await ops_test.model.deploy(
            "magma-orc8r-orchestrator",
            application_name=ORCHESTRATOR_APPLICATION_NAME,
            channel="edge",
            trust=True,
        )
        await ops_test.model.add_relation(
            relation1=f"{ORCHESTRATOR_APPLICATION_NAME}:cert-admin-operator",
            relation2="orc8r-certifier:cert-admin-operator",
        )
        await ops_test.model.add_relation(
            relation1=f"{ORCHESTRATOR_APPLICATION_NAME}:metrics-endpoint",
            relation2="orc8r-prometheus-cache:metrics-endpoint",
        )
        await ops_test.model.add_relation(
            relation1=f"{ORCHESTRATOR_APPLICATION_NAME}:magma-orc8r-accessd",
            relation2="orc8r-accessd:magma-orc8r-accessd",
        )
        await ops_test.model.add_relation(
            relation1=f"{ORCHESTRATOR_APPLICATION_NAME}:magma-orc8r-service-registry",
            relation2="orc8r-service-registry:magma-orc8r-service-registry",
        )
        await ops_test.model.wait_for_idle(
            apps=[ORCHESTRATOR_APPLICATION_NAME], status="active", timeout=1000
        )

    @pytest.fixture(scope="module")
    @pytest.mark.abort_on_fail
    async def build_and_deploy(self, ops_test, setup):
        charm = await ops_test.build_charm(".")
        resources = {
            f"{CHARM_NAME}-image": METADATA["resources"][f"{CHARM_NAME}-image"]["upstream-source"],
        }
        await ops_test.model.deploy(
            charm, resources=resources, application_name=APPLICATION_NAME, trust=True
        )

    @pytest.mark.abort_on_fail
    async def test_wait_for_blocked_status(self, ops_test, build_and_deploy):
        await ops_test.model.wait_for_idle(apps=[APPLICATION_NAME], status="blocked", timeout=1000)

    async def test_relate_and_wait_for_idle(self, ops_test, build_and_deploy):
        await ops_test.model.add_relation(
            relation1=f"{APPLICATION_NAME}:alertmanager-k8s",
            relation2="orc8r-alertmanager:alerting",
        )
        await ops_test.model.add_relation(
            relation1=f"{APPLICATION_NAME}:magma-orc8r-orchestrator",
            relation2="orc8r-orchestrator:magma-orc8r-orchestrator",
        )
        await ops_test.model.add_relation(
            relation1=f"{APPLICATION_NAME}:prometheus-k8s",
            relation2="orc8r-prometheus:self-metrics-endpoint",
        )
        await ops_test.model.add_relation(
            relation1=f"{APPLICATION_NAME}:prometheus-configurer-k8s",
            relation2="orc8r-prometheus-configurer:prometheus-configurer",
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
            apps=[APPLICATION_NAME], status="active", timeout=1000, wait_for_exact_units=1
        )
