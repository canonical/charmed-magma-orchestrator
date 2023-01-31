#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.


import logging
import shutil
import time
from typing import Tuple

import jinja2
import pytest
import requests  # type: ignore[import]
from pytest_operator.plugin import OpsTest

from render_bundle import render_bundle
from tests.integration.orchestrator import Orc8r

logger = logging.getLogger(__name__)
DOMAIN = "pizza.com"
INTEGRATION_TESTS_DIR = "tests/integration"

ORCHESTRATOR_CHARMS = [
    "fluentd-elasticsearch",
    "nms-magmalte",
    "nms-nginx-proxy",
    "orc8r-accessd",
    "orc8r-analytics",
    "orc8r-bootstrapper",
    "orc8r-certifier",
    "orc8r-configurator",
    "orc8r-ctraced",
    "orc8r-device",
    "orc8r-directoryd",
    "orc8r-dispatcher",
    "orc8r-eventd",
    "orc8r-ha",
    "orc8r-lte",
    "orc8r-metricsd",
    "orc8r-nginx",
    "orc8r-obsidian",
    "orc8r-orchestrator",
    "orc8r-policydb",
    "orc8r-service-registry",
    "orc8r-smsd",
    "orc8r-state",
    "orc8r-streamer",
    "orc8r-subscriberdb",
    "orc8r-subscriberdb-cache",
    "orc8r-tenants",
]

ORCHESTRATOR_APPS = [
    "fluentd",
    "nms-magmalte",
    "nms-nginx-proxy",
    "orc8r-accessd",
    "orc8r-analytics",
    "orc8r-bootstrapper",
    "orc8r-certifier",
    "orc8r-configurator",
    "orc8r-ctraced",
    "orc8r-device",
    "orc8r-directoryd",
    "orc8r-dispatcher",
    "orc8r-eventd",
    "orc8r-ha",
    "orc8r-lte",
    "orc8r-metricsd",
    "orc8r-nginx",
    "orc8r-obsidian",
    "orc8r-orchestrator",
    "orc8r-policydb",
    "orc8r-service-registry",
    "orc8r-smsd",
    "orc8r-state",
    "orc8r-streamer",
    "orc8r-subscriberdb",
    "orc8r-subscriberdb-cache",
    "orc8r-tenants",
]


async def run_get_load_balancer_services_action(
    ops_test: OpsTest,
) -> Tuple[str, str, str, str, str]:
    """Runs `get-load-balancer-services` on the `orc8r-orchestrator/0` unit.

    Args:
        ops_test (OpsTest): OpsTest

    Returns:
        (str, str, str, str, str): External loadbalancer IP's in the following order:
            - orc8r-bootstrap-nginx
            - orc8r-clientcert-nginx
            - orc8r-nginx-proxy
            - nginx-proxy
            - fluentd
    """
    orc8r_orchestrator_unit = ops_test.model.units["orc8r-orchestrator/0"]  # type: ignore[union-attr]  # noqa: E501
    load_balancer_action = await orc8r_orchestrator_unit.run_action(
        action_name="get-load-balancer-services"
    )
    load_balancer_action_output = await ops_test.model.get_action_output(  # type: ignore[union-attr]  # noqa: E501
        action_uuid=load_balancer_action.entity_id, wait=240
    )
    return (
        load_balancer_action_output["orc8r-bootstrap-nginx"],
        load_balancer_action_output["orc8r-clientcert-nginx"],
        load_balancer_action_output["orc8r-nginx-proxy"],
        load_balancer_action_output["nginx-proxy"],
        load_balancer_action_output["fluentd"],
    )


async def run_get_pfx_password_action(ops_test: OpsTest) -> str:
    """Runs `get-pfx-package-password` action on the `orc8r-certifier/0` unit.

    Args:
        ops_test (OpsTest): OpsTest

    Returns:
        str: PFX package password
    """
    orc8r_certifier_unit = ops_test.model.units["orc8r-certifier/0"]  # type: ignore[union-attr]  # noqa: E501
    pfx_password_action = await orc8r_certifier_unit.run_action(
        action_name="get-pfx-package-password"
    )
    pfx_password_action_output = await ops_test.model.get_action_output(  # type: ignore[union-attr]  # noqa: E501
        action_uuid=pfx_password_action.entity_id, wait=240
    )
    return pfx_password_action_output["password"]


async def get_pfx_package(ops_test: OpsTest) -> str:
    """SCP's admin_operator.pfx package from certifier container to locally.

    Args:
        ops_test (OpsTest): OpsTest

    Returns:
        str: pfx package path
    """
    export_path = "admin_operator.pfx"
    run_args = [
        "juju",
        "scp",
        "--container=magma-orc8r-certifier",
        "orc8r-certifier/0:/var/opt/magma/certs/admin_operator.pfx",
        export_path,
    ]
    retcode, stdout, stderr = await ops_test.run(*run_args)
    if retcode != 0:
        raise RuntimeError(f"Error: {stderr}")
    return export_path


async def deploy_bundle(ops_test: OpsTest, bundle_path: str, overlay_file_path: str):
    run_args = [
        "juju",
        "deploy",
        f"./{bundle_path}",
        "--trust",
        f"--overlay={overlay_file_path}",
    ]
    retcode, stdout, stderr = await ops_test.run(*run_args)
    if retcode != 0:
        raise RuntimeError(f"Error: {stderr}")
    await ops_test.model.wait_for_idle(  # type: ignore[union-attr]
        apps=ORCHESTRATOR_APPS,
        status="active",
        timeout=2000,
    )


async def pack_charm(ops_test: OpsTest, charm_directory: str, export_path: str) -> None:
    """Packs a charm based on provided directory

    Args:
        ops_test: OpsTest
        charm_directory: Charm directory
        export_path: Directory to export built charm

    Returns:
        None
    """
    charm = await ops_test.build_charm(charm_directory)
    shutil.copy(charm, export_path)
    return


def render_overlay_file(jinja_template_path: str, destination_file_path: str) -> None:
    """Renders overlay file based on jinja template.

    Args:
        jinja_template_path: Destination to Jinja template path
        destination_file_path: Destination file path

    Returns:
        None
    """
    with open(jinja_template_path, "r") as template_file:
        jinja_template = jinja2.Template(template_file.read(), autoescape=True)
    with open(destination_file_path, "wt") as output_file:
        jinja_template.stream(domain=DOMAIN).dump(output_file)


class TestOrc8rBundle:
    @pytest.fixture(scope="module")
    @pytest.mark.abort_on_fail
    async def pack_charms_and_deploy_bundle(self, ops_test: OpsTest):
        overlay_jinja_template_path = f"{INTEGRATION_TESTS_DIR}/overlay.yaml.j2"
        bundle_jinja_template_path = "bundle.yaml.j2"
        overlay_file_path = f"{INTEGRATION_TESTS_DIR}/overlay.yaml"
        bundle_file_path = f"{INTEGRATION_TESTS_DIR}/bundle.yaml"
        for app_name in ORCHESTRATOR_CHARMS:
            await pack_charm(
                ops_test=ops_test,
                charm_directory=f"../{app_name}-operator",
                export_path=f"{INTEGRATION_TESTS_DIR}/",
            )
        render_bundle(
            template=bundle_jinja_template_path,
            output=bundle_file_path,
            local=True,
        )
        render_overlay_file(
            jinja_template_path=overlay_jinja_template_path,
            destination_file_path=overlay_file_path,
        )
        await deploy_bundle(
            ops_test=ops_test, bundle_path=bundle_file_path, overlay_file_path=overlay_file_path
        )

    async def test_given_bundle_deployed_when_set_api_client_then_magma_returns_200(
        self, ops_test: OpsTest, pack_charms_and_deploy_bundle
    ):
        (
            orc8r_bootstrap_nginx_ip,
            orc8r_clientcert_nginx_ip,
            orc8r_nginx_proxy_ip,
            nginx_proxy_ip,
            fluentd_ip,
        ) = await run_get_load_balancer_services_action(ops_test)
        pfx_password = await run_get_pfx_password_action(ops_test)
        pfx_package_path = await get_pfx_package(ops_test)
        orc8r = Orc8r(
            url=f"https://{orc8r_nginx_proxy_ip}/magma/v1/",
            admin_operator_pfx_path=pfx_package_path,
            admin_operator_pfx_password=pfx_password,
        )
        timeout = 300
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = orc8r.get(endpoint="lte")
                assert response.status_code == 200
                return
            except (requests.exceptions.HTTPError, requests.exceptions.ConnectTimeout) as e:
                logger.error(e)
                time.sleep(5)
        raise TimeoutError("Could not connect to Orc8r API")
