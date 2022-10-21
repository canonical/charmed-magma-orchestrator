#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Periodically fetches and aggregates metrics."""

from charms.magma_orc8r_libs.v0.orc8r_base import Orc8rBase
from charms.observability_libs.v1.kubernetes_service_patch import (
    KubernetesServicePatch,
    ServicePort,
)
from ops.charm import CharmBase, InstallEvent
from ops.main import main


class MagmaOrc8rAnalyticsCharm(CharmBase):
    """An instance of this object everytime an event occurs."""

    BASE_CONFIG_PATH = "/var/opt/magma/configs/orc8r"

    # TODO: The various URL's should be provided through relationships.
    PROMETHEUS_URL = "http://orc8r-prometheus:9090"
    ALERTMANAGER_URL = "http://orc8r-alertmanager:9093"

    def __init__(self, *args):
        """Uses the Orc8rBase library to manage events."""
        super().__init__(*args)
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[ServicePort(name="grpc", port=9180, targetPort=9200)],
            additional_labels={"app.kubernetes.io/part-of": "orc8r-app"},
        )
        startup_command = (
            "/usr/bin/envdir "
            "/var/opt/magma/envdir "
            "/var/opt/magma/bin/analytics "
            "-logtostderr=true "
            "-v=0"
        )
        self._orc8r_base = Orc8rBase(self, startup_command=startup_command)
        self.framework.observe(self.on.install, self._on_install)

    def _on_install(self, event: InstallEvent):
        if not self._orc8r_base.container.can_connect():
            event.defer()
            return
        self._write_config_file()

    def _write_config_file(self):
        metricsd_config = (
            f'prometheusQueryAddress: "{self.PROMETHEUS_URL}"\n'
            f'alertmanagerApiURL: "{self.ALERTMANAGER_URL}/api/v2"\n'
            '"profile": "prometheus"\n'
        )
        analytics_config = (
            '"appID": ""\n'
            '"appSecret": ""\n'
            '"categoryName": "magma"\n'
            '"exportMetrics": false\n'
            '"metricExportURL": ""\n'
            '"metricsPrefix": ""\n'
        )
        self._orc8r_base.container.push(f"{self.BASE_CONFIG_PATH}/metricsd.yml", metricsd_config)
        self._orc8r_base.container.push(f"{self.BASE_CONFIG_PATH}/analytics.yml", analytics_config)


if __name__ == "__main__":
    main(MagmaOrc8rAnalyticsCharm)
