#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.


from pathlib import Path
from typing import Optional
from integration_constatns import *

def find_charm(charm_dir: str, charm_file_name: str) -> Optional[str]:
    """Locates a specific charm.

        Args:
            charm_dir (str): Charm dir to search in
            charm_file_name (str)

        Returns:
            str: path to charm
        """
    try:
        path = next(Path(charm_dir).rglob(charm_file_name))
        return str(path)
    except StopIteration:
        return None


async def deploy_postgresql(ops_test):
    """Deploys postgresql charm."""
    await ops_test.model.deploy("postgresql-k8s", application_name=DB_APPLICATION_NAME)

async def deploy_tls_certificates_operator(ops_test):
    """Deploys tls-certificates-operator charm."""
    await ops_test.model.deploy(
        "tls-certificates-operator",
        application_name="tls-certificates-operator",
        config={
            "generate-self-signed-certificates": True,
            "ca-common-name": "rootca.whatever.com",
        },
        channel="edge",
    )


async def deploy_orc8r_certifier(ops_test):
    """Deploys orc8r-certifier-operator charm."""
    certifier_charm = find_charm(
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
        config={"domain": "whatever.com"},
        trust=True,
        series="jammy",
    )
    await ops_test.model.add_relation(
        relation1=CERTIFIER_APPLICATION_NAME, relation2="postgresql-k8s:db"
    )
    await ops_test.model.add_relation(
        relation1=CERTIFIER_APPLICATION_NAME, relation2="tls-certificates-operator"
    )

async def deploy_grafana_k8s_operator(ops_test):
    """Deploys grafana-k8 charm."""
    await ops_test.model.deploy(
        "grafana-k8s",
        application_name="grafana-k8s",
        channel="edge",
        trust=True,
    )

async def deploy_prometheus_configurer(ops_test):
    """Deploys prometheus-configurer-k8s charm"""
    await ops_test.model.deploy(
        "prometheus-configurer-k8s",
        application_name="orc8r-prometheus-configurer",
        channel="edge",
        trust=True,
    )
    await ops_test.model.add_relation(
        relation1="orc8r-prometheus-configurer",
        relation2="orc8r-prometheus:receive-remote-write",
    )

async def deploy_prometheus_k8s_operator(ops_test):
    """Deploys prometheus-k8s charm."""
    await ops_test.model.deploy(
        "prometheus-k8s", application_name="prometheus-k8s", channel="edge", trust=True
    )
    await ops_test.model.add_relation(
        relation1="prometheus-k8s:grafana-source", relation2="grafana-k8s"
    )

async def deploy_nms_magmalte(ops_test):
    """Deploys nms-magmalte-operator charm."""
    magmalte_charm = find_charm(
        "../nms-magmalte-operator", NMS_MAGMALTE_CHARM_FILE_NAME)
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
        series="jammy",
    )
    await ops_test.model.add_relation(
        relation1=NMS_MAGMALTE_APPLICATION_NAME, relation2="postgresql-k8s:db"
    )
    await ops_test.model.add_relation(
        relation1=NMS_MAGMALTE_APPLICATION_NAME,
        relation2="orc8r-certifier:cert-admin-operator",
    )
    await ops_test.model.add_relation(
        relation1=f"{NMS_MAGMALTE_APPLICATION_NAME}:grafana-auth",
        relation2="grafana-k8s",
    )


async def deploy_prometheus_cache(ops_test):
    """Deploys "prometheus-edge-hub" charm"""
    await ops_test.model.deploy(
        "prometheus-edge-hub",
        application_name="orc8r-prometheus-cache",
        channel="edge",
        trust=True,
    )

async def deploy_alertmanager(ops_test):
    """Deploys alertmanager-k8s charm"""
    await ops_test.model.deploy(
        "alertmanager-k8s",
        application_name="orc8r-alertmanager",
        channel="edge",
        trust=True,
    )

async def deploy_alertmanager_configurer(ops_test):
    """Deploys alertmanager-configurer-k8s charm"""
    await ops_test.model.deploy(
        "alertmanager-configurer-k8s",
        application_name="orc8r-alertmanager-configurer",
        channel="edge",
        trust=True,
        series="jammy",
    )
    await ops_test.model.add_relation(
        relation1="orc8r-alertmanager-configurer:alertmanager",
        relation2="orc8r-alertmanager:remote-configuration",
    )


async def deploy_orc8r_service_registry(ops_test):
    """Deploys orc8r-service-registry-operator charm"""
    service_registry_charm = find_charm(
        "../orc8r-service-registry-operator", SERVICE_REGISTRY_CHARM_FILE_NAME
        )
    if not service_registry_charm:
        service_registry_charm = await ops_test.build_charm(
            "../orc8r-service-registry-operator"
        )
    resources = {
        f"{SERVICE_REGISTRY_CHARM_NAME}-image": SERVICE_REGISTRY_METADATA["resources"][
            f"{SERVICE_REGISTRY_CHARM_NAME}-image"
        ]["upstream-source"],
    }
    await ops_test.model.deploy(
        service_registry_charm,
        resources=resources,
        application_name=SERVICE_REGISTRY_APPLICATION_NAME,
        trust=True,
        series="jammy",
    )


async def deploy_orc8r_accessd(ops_test):
    """Deploys orc8r-accessd-operator charm"""
    accessd_charm = find_charm(
        "../orc8r-accessd-operator", ACCESSD_CHARM_FILE_NAME)
    if not accessd_charm:
        accessd_charm = await ops_test.build_charm("../orc8r-accessd-operator/")
    resources = {
        f"{ACCESSD_CHARM_NAME}-image": ACCESSD_METADATA["resources"][
            f"{ACCESSD_CHARM_NAME}-image"
        ]["upstream-source"],
    }
    await ops_test.model.deploy(
        accessd_charm,
        resources=resources,
        application_name=ACCESSD_APPLICATION_NAME,
        trust=True,
        series="jammy",
    )
    await ops_test.model.add_relation(
        relation1=ACCESSD_APPLICATION_NAME, relation2="postgresql-k8s:db"
    )

async def deploy_orc8r_orchestrator(ops_test):
    """Deploys orc8r-orchestrator-operator charm"""
    orchestrator_charm = find_charm(
        "../orc8r-orchestrator-operator", ORCHESTRATOR_CHARM_FILE_NAME
    )
    if not orchestrator_charm:
        orchestrator_charm = await ops_test.build_charm("../orc8r-orchestrator-operator/")
    resources = {
        f"{ORCHESTRATOR_CHARM_NAME}-image": ORCHESTRATOR_METADATA["resources"][
            f"{ORCHESTRATOR_CHARM_NAME}-image"
        ]["upstream-source"],
    }
    await ops_test.model.deploy(
        orchestrator_charm,
        resources=resources,
        application_name=ORCHESTRATOR_APPLICATION_NAME,
        trust=True,
        series="jammy",
    )
    await ops_test.model.add_relation(
        relation1=f"{ORCHESTRATOR_APPLICATION_NAME}:cert-admin-operator",
        relation2="orc8r-certifier:cert-admin-operator",
    )
    await ops_test.model.add_relation(
        relation1=f"{ORCHESTRATOR_APPLICATION_NAME}:magma-orc8r-certifier",
        relation2="orc8r-certifier:magma-orc8r-certifier",
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

async def deploy_bootstrapper(ops_test):
    """Deploys orc8r-bootstrapper-operator charm"""
    bootstrapper_charm = find_charm(
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
        relation1=BOOTSTRAPPER_APPLICATION_NAME, relation2="postgresql-k8s:db"
    )
    await ops_test.model.add_relation(
        relation1=BOOTSTRAPPER_APPLICATION_NAME, relation2="orc8r-certifier:cert-root-ca"
    )

async def deploy_orc8r_obsidian(ops_test):
    """Deploys orc8r-obsidian-operator charm"""
    obsidian_charm = find_charm("../orc8r-obsidian-operator", OBSIDIAN_CHARM_FILE_NAME)
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

async def remove_postgresql(ops_test):
    """Removes the database charm."""
    await ops_test.model.remove_application(
            DB_APPLICATION_NAME, block_until_done=True, force=True
    )

async def redeploy_and_relate_postgresql(ops_test):
    """Deploys the database charm and relates it to all charms that require it."""
    await deploy_postgresql(ops_test)
    for requirer in DB_REQUIRER_ORC8R_CHARMS:
        if _application_is_deployed(ops_test, requirer):
            await ops_test.model.add_relation(
                relation1=requirer, relation2="postgresql-k8s:db"
            )

def _application_is_deployed(ops_test, app_name):
    try:
        ops_test.model.get_app(app_name)
        return True
    except:
        return False