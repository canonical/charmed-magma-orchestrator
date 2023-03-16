#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import sys
from pathlib import Path  # noqa: E402

sys.path.append("./../")
import common.integration_helpers.helpers as helpers  # type: ignore[import]  # noqa: E402
import pytest  # noqa: E402
import yaml  # noqa: E402

from charm import MagmaOrc8rStateCharm  # noqa: E402

logger = logging.getLogger(__name__)
METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())

APPLICATION_NAME = SERVICE_NAME = "orc8r-state"
CHARM_NAME = "magma-orc8r-state"
CHARM_RESOURCES = {
    f"{CHARM_NAME}-image": METADATA["resources"][f"{CHARM_NAME}-image"]["upstream-source"],
}
with open("./src/charm.py") as charm_py:
    CHARM_SOURCE_CODE = charm_py.read()


class TestOrc8rStateUpgrade:
    @pytest.fixture(scope="module")
    @pytest.mark.abort_on_fail
    async def setup(self, ops_test):
        await helpers.deploy_postgresql(ops_test)
        await helpers.deploy_orc8r_charm_from_1_6_stable_channel(
            ops_test,
            charm_name=CHARM_NAME,
            application_name=APPLICATION_NAME,
        )
        await helpers.relate_orc8r_charm_with_postgresql(
            ops_test,
            application_name=APPLICATION_NAME,
        )
        await ops_test.model.wait_for_idle(apps=[APPLICATION_NAME], status="active", timeout=600)

    @pytest.fixture(scope="module")
    @pytest.mark.abort_on_fail
    async def build_and_refresh(self, ops_test, setup):
        charm = await ops_test.build_charm(".")

        await helpers.juju_refresh_application(
            ops_test,
            application_name=APPLICATION_NAME,
            path=str(charm),
            resources=CHARM_RESOURCES,
        )

    @pytest.mark.abort_on_fail
    async def test_wait_for_active_idle_after_refresh(self, ops_test, setup, build_and_refresh):
        await ops_test.model.wait_for_idle(apps=[APPLICATION_NAME], status="active", timeout=180)

    @pytest.mark.abort_on_fail
    async def test_workload_container_image_updated_with_metadata_oci_image(
        self, ops_test, setup, build_and_refresh
    ):
        image = await helpers.get_container_image(ops_test, APPLICATION_NAME)
        assert image == CHARM_RESOURCES[f"{CHARM_NAME}-image"]

    @pytest.mark.abort_on_fail
    async def test_charm_source_code_in_charm_container_is_updated(
        self, ops_test, setup, build_and_refresh
    ):
        charm_container_src = helpers.get_content_of_file_from_container(
            ops_test,
            f"{APPLICATION_NAME}/0",
            "charm",
            f"/var/lib/juju/agents/unit-{APPLICATION_NAME}-0/charm/src/charm.py",
        )
        assert charm_container_src.replace("\r\n", "") == CHARM_SOURCE_CODE.replace("\n", "")

    @pytest.mark.abort_on_fail
    async def test_workload_process_started_by_correct_command(
        self, ops_test, setup, build_and_refresh
    ):
        processes = helpers.get_processes_running_in_the_container(
            ops_test,
            f"{APPLICATION_NAME}/0",
            CHARM_NAME,
        )
        assert MagmaOrc8rStateCharm.STARTUP_COMMAND in processes.values()

    @pytest.mark.abort_on_fail
    async def test_charm_channel_doesnt_point_to_1_6_stable(
        self, ops_test, setup, build_and_refresh
    ):
        app_details = await helpers.get_juju_application_details(ops_test, APPLICATION_NAME)
        assert "1.6/stable" not in app_details[APPLICATION_NAME]["channel"]

    @pytest.mark.abort_on_fail
    async def test_workload_services_match_charm_config(self, ops_test, setup, build_and_refresh):
        expected_ports = [
            {"name": "grpc", "port": 9180, "protocol": "TCP", "targetPort": 9105},
            {"name": "grpc-internal", "port": 9190, "protocol": "TCP", "targetPort": 9305},
        ]
        service_details = await helpers.get_service_details(ops_test, SERVICE_NAME)
        service_ports = service_details["spec"]["ports"]

        assert service_ports == expected_ports
