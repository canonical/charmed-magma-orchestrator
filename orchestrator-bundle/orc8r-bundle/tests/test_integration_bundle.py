import logging

import pytest
from pytest_operator.plugin import OpsTest  # type: ignore[import]  # noqa: F401

logger = logging.getLogger(__name__)

POSTGRES="postgresql-k8s"
ORC8R_CHARMS = ["nms-magmalte",
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
"orc8r-tenants"]


class TestBundle:
    
    @pytest.mark.abort_on_fail
    async def test_bundle(self, ops_test, setup):
        await ops_test.model.wait_for_idle(apps[POSTGRES], status="active", timeout=1000)
        for charm in ORC8R_CHARMS:
            await ops_test.model.wait_for_idle(apps=[charm], status="active", timeout=1000)