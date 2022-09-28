#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.


from typing import Tuple

import jinja2
import pytest
from pytest_operator.plugin import OpsTest
from python_hosts import Hosts, HostsEntry  # type: ignore[import]

from tests.integration.orchestrator import Orc8r

DOMAIN = "pizza.com"


def update_etc_host(
    orc8r_bootstrap_nginx_ip: str,
    orc8r_nginx_proxy_ip: str,
    orc8r_clientcert_nginx_ip: str,
    nginx_proxy_ip: str,
) -> None:

    hosts = Hosts(path="/etc/hosts")
    bootstrapper_controller_entry = HostsEntry(
        entry_type="ipv4",
        address=orc8r_bootstrap_nginx_ip,
        names=[f"bootstrapper-controller.{DOMAIN}"],
    )
    orc8r_nginx_entry = HostsEntry(
        entry_type="ipv4", address=orc8r_nginx_proxy_ip, names=[f"api.{DOMAIN}"]
    )
    orc8r_clientcert_entry = HostsEntry(
        entry_type="ipv4", address=orc8r_clientcert_nginx_ip, names=[f"controller.{DOMAIN}"]
    )
    nginx_proxy_entry = HostsEntry(
        entry_type="ipv4",
        address=nginx_proxy_ip,
        names=[f"master.nms.{DOMAIN}", f"magma-test.nms.{DOMAIN}"],
    )

    hosts.add(
        [
            bootstrapper_controller_entry,
            orc8r_nginx_entry,
            orc8r_clientcert_entry,
            nginx_proxy_entry,
        ]
    )
    hosts.write()


async def run_get_load_balancer_services_action(ops_test: OpsTest) -> Tuple[str, str, str, str]:
    """Runs `get-load-balancer-services` on the `orc8r-orchestrator/0` unit.

    Args:
        ops_test (OpsTest): opstest object

    Returns:
        (str, str, str, str): External loadbalancer IP's

    """
    orc8r_orchestrator_unit = ops_test.model.units["orc8r-orchestrator/0"]  # type: ignore[union-attr]  # noqa: E501
    load_balancer_action = await orc8r_orchestrator_unit.run_action(
        action_name="get-load-balancer-services"
    )
    load_balancer_action_output = await ops_test.model.get_action_output(  # type: ignore[union-attr]  # noqa: E501
        action_uuid=load_balancer_action.entity_id, wait=60
    )
    return (
        load_balancer_action_output["orc8r-bootstrap-nginx"],
        load_balancer_action_output["orc8r-clientcert-nginx"],
        load_balancer_action_output["orc8r-clientcert-nginx"],
        load_balancer_action_output["nginx-proxy"],
    )


async def run_get_pfx_password_action(ops_test: OpsTest) -> str:
    """Runs `get-pfx-package-password` action on the `orc8r-certifier/0` unit.

    Args:
        ops_test (OpsTest): opstest object

    Returns:
        str: PFX package password
    """
    orc8r_certifier_unit = ops_test.model.units["orc8r-certifier/0"]  # type: ignore[union-attr]  # noqa: E501
    pfx_password_action = await orc8r_certifier_unit.run_action(
        action_name="get-pfx-package-password"
    )
    pfx_password_action_output = await ops_test.model.get_action_output(  # type: ignore[union-attr]  # noqa: E501
        action_uuid=pfx_password_action.entity_id, wait=60
    )
    return pfx_password_action_output["password"]


async def get_pfx_package(ops_test: OpsTest) -> str:
    """SCP's admin_operator.pfx package from certifier container to locally.

    Args:
        ops_test (OpsTest): opstest object

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


class TestOrc8rBundle:
    @pytest.fixture(scope="module")
    @pytest.mark.abort_on_fail
    async def deploy_bundle_and_wait_for_idle(self, ops_test: OpsTest):
        overlay_file_path = "tests/integration/overlay.yaml"
        orc8r_applications = [
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
            "tls-certificates-operator",
        ]
        with open("tests/integration/overlay.yaml.j2", "r") as t:
            jinja_template = jinja2.Template(t.read(), autoescape=True)
        with open(overlay_file_path, "wt") as o:
            jinja_template.stream(domain=DOMAIN).dump(o)
        run_args = [
            "juju",
            "deploy",
            "magma-orc8r",
            "--trust",
            "--channel=edge",
            f"--overlay={overlay_file_path}",
        ]
        retcode, stdout, stderr = await ops_test.run(*run_args)
        if retcode != 0:
            raise RuntimeError(f"Error: {stderr}")
        await ops_test.model.wait_for_idle(  # type: ignore[union-attr]
            apps=orc8r_applications,
            status="active",
            timeout=1000,
        )

    async def test_given_bundle_deployed_when_set_api_client_then_magma_returns_200(
        self, ops_test: OpsTest, deploy_bundle_and_wait_for_idle
    ):
        (
            orc8r_bootstrap_nginx_ip,
            orc8r_clientcert_nginx_ip,
            orc8r_nginx_proxy_ip,
            nginx_proxy_ip,
        ) = await run_get_load_balancer_services_action(ops_test)
        pfx_password = await run_get_pfx_password_action(ops_test)
        update_etc_host(
            orc8r_bootstrap_nginx_ip=orc8r_bootstrap_nginx_ip,
            orc8r_clientcert_nginx_ip=orc8r_clientcert_nginx_ip,
            orc8r_nginx_proxy_ip=orc8r_nginx_proxy_ip,
            nginx_proxy_ip=nginx_proxy_ip,
        )
        pfx_package_path = await get_pfx_package(ops_test)

        orc8r = Orc8r(
            url=f"https://api.{DOMAIN}/magma/v1/",
            admin_operator_pfx_path=pfx_package_path,
            admin_operator_pfx_password=pfx_password,
        )
        response = orc8r.get(endpoint="lte")

        assert response.status_code == 200
