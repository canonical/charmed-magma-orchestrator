#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Functions commonly used by integration testing of different magma orc8r components."""  # noqa: E501

from pathlib import Path
from typing import Optional

from pytest_operator.plugin import OpsTest

import integration_test_utils.integration_constants as itest_const


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


async def deploy_postgresql(
    ops_test: OpsTest,
    channel: str = "latest/stable",
) -> None:
    """Deploys postgresql charm.

    Args:
        ops_test
        channel (str): channel from which the charm will be deployed
    """
    await ops_test.model.deploy(  # type: ignore[union-attr]
        itest_const.DB_CHARM_NAME,
        application_name=itest_const.DB_CHARM_NAME,
        channel=channel,
        trust=True,
    )


async def deploy_tls_certificates_operator(
    ops_test: OpsTest,
    channel: str = "latest/stable",
) -> None:
    """Deploys tls-certificates-operator charm.

    Args:
        ops_test (OpsTest)
        channel (str): channel from which the charm will be deployed
    """
    await ops_test.model.deploy(  # type: ignore[union-attr]
        itest_const.TLS_CERTIFICATES_CHARM_NAME,
        application_name=itest_const.TLS_CERTIFICATES_CHARM_NAME,
        config={
            "generate-self-signed-certificates": True,
            "ca-common-name": "rootca.whatever.com",
        },
        channel=channel,
    )


async def deploy_orc8r_certifier(ops_test: OpsTest) -> None:
    """Deploys orc8r-certifier-operator charm.

    Args:
        ops_test (OpsTest)
    """
    certifier_charm = find_charm(
        "../orc8r-certifier-operator", itest_const.CERTIFIER_CHARM_FILE_NAME
    )
    if not certifier_charm:
        certifier_charm = await ops_test.build_charm(  # type: ignore[assignment]  # noqa: E501
            "../orc8r-certifier-operator/",
        )
    resources = {
        f"{itest_const.CERTIFIER_CHARM_NAME}-image": itest_const.CERTIFIER_METADATA[  # noqa: E501
            "resources"
        ][
            f"{itest_const.CERTIFIER_CHARM_NAME}-image"
        ][
            "upstream-source"
        ],
    }
    await ops_test.model.deploy(  # type: ignore[union-attr]
        certifier_charm,
        resources=resources,
        application_name=itest_const.CERTIFIER_APPLICATION_NAME,
        config={"domain": "whatever.com"},
        trust=True,
        series="jammy",
    )
    await ops_test.model.add_relation(  # type: ignore[union-attr]
        relation1=itest_const.CERTIFIER_APPLICATION_NAME,
        relation2=f"{itest_const.DB_CHARM_NAME}:database",
    )
    await ops_test.model.add_relation(  # type: ignore[union-attr]
        relation1=itest_const.CERTIFIER_APPLICATION_NAME,
        relation2=itest_const.TLS_CERTIFICATES_CHARM_NAME,
    )


async def deploy_grafana_k8s_operator(
    ops_test: OpsTest,
    channel: str = "latest/stable",
) -> None:
    """Deploys grafana-k8 charm.

    Args:
        ops_test (OpsTest)
        channel (str): channel from which the charm will be deployed
    """
    await ops_test.model.deploy(  # type: ignore[union-attr]
        itest_const.GRAFANA_K8S_CHARM_NAME,
        application_name=itest_const.GRAFANA_K8S_CHARM_NAME,
        channel=channel,
        trust=True,
    )


async def deploy_prometheus_configurer(
    ops_test: OpsTest,
    channel: str = "latest/stable",
) -> None:
    """Deploys prometheus-configurer-k8s charm.

    Args:
        ops_test (OpsTest)
        channel (str): channel from which the charm will be deployed
    """
    await ops_test.model.deploy(  # type: ignore[union-attr]
        itest_const.PROMETHEUS_CONFIGURER_K8S_CHARM_NAME,
        application_name=itest_const.PROMETHEUS_CONFIGURER_K8S_CHARM_NAME,
        channel=channel,
        trust=True,
    )
    await ops_test.model.add_relation(  # type: ignore[union-attr]
        relation1=itest_const.PROMETHEUS_CONFIGURER_K8S_CHARM_NAME,
        relation2=f"{itest_const.PROMETHEUS_K8S_CHARM_NAME}:receive-remote-write",  # noqa: E501
    )


async def deploy_prometheus_k8s_operator(
    ops_test: OpsTest,
    channel: str = "latest/stable",
) -> None:
    """Deploys prometheus-k8s charm.

    Args:
        ops_test (OpsTest)
        channel (str): channel from which the charm will be deployed
    """
    await ops_test.model.deploy(  # type: ignore[union-attr]
        itest_const.PROMETHEUS_K8S_CHARM_NAME,
        application_name=itest_const.PROMETHEUS_K8S_CHARM_NAME,
        channel=channel,
        trust=True,
    )
    await ops_test.model.add_relation(  # type: ignore[union-attr]
        relation1=f"{itest_const.PROMETHEUS_K8S_CHARM_NAME}:grafana-source",
        relation2=itest_const.GRAFANA_K8S_CHARM_NAME,
    )


async def deploy_nms_magmalte(ops_test: OpsTest) -> None:
    """Deploys nms-magmalte-operator charm.

    Args:
        ops_test (OpsTest)
    """
    magmalte_charm = find_charm(
        "../nms-magmalte-operator",
        itest_const.NMS_MAGMALTE_CHARM_FILE_NAME,
    )

    if not magmalte_charm:
        magmalte_charm = await ops_test.build_charm(  # type: ignore[assignment]  # noqa: E501
            "../nms-magmalte-operator/",
        )
    resources = {
        f"{itest_const.NMS_MAGMALTE_CHARM_NAME}-image": itest_const.NMS_MAGMALTE_METADATA[  # noqa: E501
            "resources"
        ][
            f"{itest_const.NMS_MAGMALTE_CHARM_NAME}-image"
        ][
            "upstream-source"
        ],
    }
    await ops_test.model.deploy(  # type: ignore[union-attr]
        magmalte_charm,
        resources=resources,
        application_name=itest_const.NMS_MAGMALTE_APPLICATION_NAME,
        trust=True,
        series="jammy",
    )
    await ops_test.model.add_relation(  # type: ignore[union-attr]
        relation1=itest_const.NMS_MAGMALTE_APPLICATION_NAME,
        relation2=f"{itest_const.DB_CHARM_NAME}:database",
    )
    await ops_test.model.add_relation(  # type: ignore[union-attr]
        relation1=itest_const.NMS_MAGMALTE_APPLICATION_NAME,
        relation2=f"{itest_const.CERTIFIER_APPLICATION_NAME}:cert-admin-operator",  # noqa: E501
    )
    await ops_test.model.add_relation(  # type: ignore[union-attr]
        relation1=f"{itest_const.NMS_MAGMALTE_APPLICATION_NAME}:grafana-auth",  # noqa: E501
        relation2=itest_const.GRAFANA_K8S_CHARM_NAME,
    )


async def deploy_prometheus_cache(
    ops_test: OpsTest,
    channel: str = "latest/stable",
) -> None:
    """Deploys prometheus-edge-hub charm.

    Args:
        ops_test (OpsTest)
        channel (str): channel from which the charm will be deployed
    """
    await ops_test.model.deploy(  # type: ignore[union-attr]
        itest_const.PROMETHEUS_CACHE_CHARM_NAME,
        application_name=itest_const.PROMETHEUS_CACHE_APPLICATION_NAME,
        channel=channel,
        trust=True,
    )


async def deploy_alertmanager(
    ops_test: OpsTest,
    channel: str = "latest/stable",
) -> None:
    """Deploys alertmanager-k8s charm.

    Args:
        ops_test (OpsTest)
        channel (str): channel from which the charm will be deployed
    """
    await ops_test.model.deploy(  # type: ignore[union-attr]
        itest_const.ALERTMANAGER_K8S_CHARM_NAME,
        application_name=itest_const.ALERTMANAGER_K8S_CHARM_NAME,
        channel=channel,
        trust=True,
    )


async def deploy_alertmanager_configurer(
    ops_test: OpsTest,
    channel: str = "latest/stable",
) -> None:
    """Deploys alertmanager-configurer-k8s charm.

    Args:
        ops_test (OpsTest)
        channel (str): channel from which the charm will be deployed
    """
    await ops_test.model.deploy(  # type: ignore[union-attr]
        itest_const.ALERTMANAGER_CONFIGURER_CHARM_NAME,
        application_name=itest_const.ALERTMANAGER_CONFIGURER_CHARM_NAME,
        channel=channel,
        trust=True,
        series="jammy",
    )
    await ops_test.model.add_relation(  # type: ignore[union-attr]
        relation1=f"{itest_const.ALERTMANAGER_CONFIGURER_CHARM_NAME}:alertmanager",  # noqa: E501
        relation2=f"{itest_const.ALERTMANAGER_K8S_CHARM_NAME}:remote-configuration",  # noqa: E501
    )


async def deploy_orc8r_service_registry(ops_test: OpsTest) -> None:
    """Deploys orc8r-service-registry-operator charm.

    Args:
        ops_test (OpsTest)
    """
    service_registry_charm = find_charm(
        "../orc8r-service-registry-operator",
        itest_const.SERVICE_REGISTRY_CHARM_FILE_NAME,
    )
    if not service_registry_charm:
        service_registry_charm = await ops_test.build_charm(  # type: ignore[assignment]  # noqa: E501
            "../orc8r-service-registry-operator",
        )
    resources = {
        f"{itest_const.SERVICE_REGISTRY_CHARM_NAME}-image": itest_const.SERVICE_REGISTRY_METADATA[  # noqa: E501
            "resources"
        ][
            f"{itest_const.SERVICE_REGISTRY_CHARM_NAME}-image"
        ][
            "upstream-source"
        ],
    }
    await ops_test.model.deploy(  # type: ignore[union-attr]
        service_registry_charm,
        resources=resources,
        application_name=itest_const.SERVICE_REGISTRY_APPLICATION_NAME,
        trust=True,
        series="jammy",
    )


async def deploy_orc8r_accessd(ops_test: OpsTest) -> None:
    """Deploys orc8r-accessd-operator charm.

    Args:
        ops_test (OpsTest)
    """
    accessd_charm = find_charm(
        "../orc8r-accessd-operator", itest_const.ACCESSD_CHARM_FILE_NAME
    )
    if not accessd_charm:
        accessd_charm = await ops_test.build_charm(  # type: ignore[assignment]
            "../orc8r-accessd-operator/",
        )
    resources = {
        f"{itest_const.ACCESSD_CHARM_NAME}-image": itest_const.ACCESSD_METADATA[  # noqa: E501
            "resources"
        ][
            f"{itest_const.ACCESSD_CHARM_NAME}-image"
        ][
            "upstream-source"
        ],
    }
    await ops_test.model.deploy(  # type: ignore[union-attr]
        accessd_charm,
        resources=resources,
        application_name=itest_const.ACCESSD_APPLICATION_NAME,
        trust=True,
        series="jammy",
    )
    await ops_test.model.add_relation(  # type: ignore[union-attr]
        relation1=itest_const.ACCESSD_APPLICATION_NAME,
        relation2=f"{itest_const.DB_CHARM_NAME}:database",
    )


async def deploy_orc8r_orchestrator(ops_test: OpsTest) -> None:
    """Deploys orc8r-orchestrator-operator charm.

    Args:
        ops_test (OpsTest)
    """
    orchestrator_charm = find_charm(
        "../orc8r-orchestrator-operator",
        itest_const.ORCHESTRATOR_CHARM_FILE_NAME,
    )
    if not orchestrator_charm:
        orchestrator_charm = await ops_test.build_charm(  # type: ignore[assignment]  # noqa: E501
            "../orc8r-orchestrator-operator/"
        )
    resources = {
        f"{itest_const.ORCHESTRATOR_CHARM_NAME}-image": itest_const.ORCHESTRATOR_METADATA[  # noqa: E501
            "resources"
        ][
            f"{itest_const.ORCHESTRATOR_CHARM_NAME}-image"
        ][
            "upstream-source"
        ],
    }
    await ops_test.model.deploy(  # type: ignore[union-attr]
        orchestrator_charm,
        resources=resources,
        application_name=itest_const.ORCHESTRATOR_APPLICATION_NAME,
        trust=True,
        series="jammy",
    )
    await ops_test.model.add_relation(  # type: ignore[union-attr]
        relation1=f"{itest_const.ORCHESTRATOR_APPLICATION_NAME}:cert-admin-operator",  # noqa: E501
        relation2="orc8r-certifier:cert-admin-operator",
    )
    await ops_test.model.add_relation(  # type: ignore[union-attr]
        relation1=f"{itest_const.ORCHESTRATOR_APPLICATION_NAME}:magma-orc8r-certifier",  # noqa: E501
        relation2=f"{itest_const.CERTIFIER_APPLICATION_NAME}:magma-orc8r-certifier",  # noqa: E501
    )
    await ops_test.model.add_relation(  # type: ignore[union-attr]
        relation1=f"{itest_const.ORCHESTRATOR_APPLICATION_NAME}:metrics-endpoint",  # noqa: E501
        relation2=f"{itest_const.PROMETHEUS_CACHE_APPLICATION_NAME}:metrics-endpoint",  # noqa: E501
    )
    await ops_test.model.add_relation(  # type: ignore[union-attr]
        relation1=f"{itest_const.ORCHESTRATOR_APPLICATION_NAME}:magma-orc8r-accessd",  # noqa: E501
        relation2=f"{itest_const.ACCESSD_APPLICATION_NAME}:magma-orc8r-accessd",  # noqa: E501
    )
    await ops_test.model.add_relation(  # type: ignore[union-attr]
        relation1=f"{itest_const.ORCHESTRATOR_APPLICATION_NAME}:magma-orc8r-service-registry",  # noqa: E501
        relation2=f"{itest_const.SERVICE_REGISTRY_APPLICATION_NAME}:magma-orc8r-service-registry",  # noqa: E501
    )


async def deploy_bootstrapper(ops_test: OpsTest) -> None:
    """Deploys orc8r-bootstrapper-operator charm.

    Args:
        ops_test (OpsTest)
    """
    bootstrapper_charm = find_charm(
        "../orc8r-bootstrapper-operator",
        itest_const.BOOTSTRAPPER_CHARM_FILE_NAME,
    )
    if not bootstrapper_charm:
        bootstrapper_charm = await ops_test.build_charm(  # type: ignore[assignment]  # noqa: E501
            "../orc8r-bootstrapper-operator/",
        )
    resources = {
        f"{itest_const.BOOTSTRAPPER_CHARM_NAME}-image": itest_const.BOOTSTRAPPER_METADATA[  # noqa: E501
            "resources"
        ][
            f"{itest_const.BOOTSTRAPPER_CHARM_NAME}-image"
        ][
            "upstream-source"
        ],
    }
    await ops_test.model.deploy(  # type: ignore[union-attr]
        bootstrapper_charm,
        resources=resources,
        application_name=itest_const.BOOTSTRAPPER_APPLICATION_NAME,
        trust=True,
        series="jammy",
    )
    await ops_test.model.add_relation(  # type: ignore[union-attr]
        relation1=itest_const.BOOTSTRAPPER_APPLICATION_NAME,
        relation2=f"{itest_const.DB_CHARM_NAME}:database",
    )
    await ops_test.model.add_relation(  # type: ignore[union-attr]
        relation1=itest_const.BOOTSTRAPPER_APPLICATION_NAME,
        relation2=f"{itest_const.CERTIFIER_APPLICATION_NAME}:cert-root-ca",
    )


async def deploy_orc8r_obsidian(ops_test: OpsTest) -> None:
    """Deploys orc8r-obsidian-operator charm.

    Args:
        ops_test (OpsTest)
    """
    obsidian_charm = find_charm(
        "../orc8r-obsidian-operator", itest_const.OBSIDIAN_CHARM_FILE_NAME
    )
    if not obsidian_charm:
        obsidian_charm = await ops_test.build_charm(  # type: ignore[assignment]  # noqa: E501
            "../orc8r-obsidian-operator/",
        )
    resources = {
        f"{itest_const.OBSIDIAN_CHARM_NAME}-image": itest_const.OBSIDIAN_METADATA[  # noqa: E501
            "resources"
        ][
            f"{itest_const.OBSIDIAN_CHARM_NAME}-image"
        ][
            "upstream-source"
        ],
    }
    await ops_test.model.deploy(  # type: ignore[union-attr]
        obsidian_charm,
        resources=resources,
        application_name=itest_const.OBSIDIAN_APPLICATION_NAME,
        trust=True,
        series="jammy",
    )


async def remove_postgresql(ops_test: OpsTest) -> None:
    """Remove the database charm.

    Args:
        ops_test (OpsTest)
    """
    await ops_test.model.remove_application(  # type: ignore[union-attr]
        itest_const.DB_CHARM_NAME, block_until_done=True, force=True
    )


async def redeploy_and_relate_postgresql(ops_test) -> None:
    """Deploys the database charm.

    Relates the db to all charms that require it in the test.

    Args:
        ops_test (OpsTest)
    """
    await deploy_postgresql(ops_test)
    for requirer in itest_const.DB_REQUIRER_ORC8R_CHARMS:
        if requirer in ops_test.model.applications:
            await ops_test.model.add_relation(
                relation1=requirer,
                relation2=f"{itest_const.DB_CHARM_NAME}:database",
            )
