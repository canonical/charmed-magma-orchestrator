#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

from charms.magma_orc8r_libs.v0.orc8r_base import Orc8rBase
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from ops.charm import CharmBase
from ops.main import main


class MagmaOrc8rAnalyticsCharm(CharmBase):

    BASE_CONFIG_PATH = "/var/opt/magma/configs/orc8r"

    def __init__(self, *args):
        """
        An instance of this object everytime an event occurs
        """
        super().__init__(*args)
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[("grpc", 9180, 9200)],
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

    def _on_install(self, event):
        self._write_config_file()

    def _write_config_file(self):
        metricsd_config = (
            'prometheusQueryAddress: "http://orc8r-prometheus:9090"\n'
            'alertmanagerApiURL: "http://orc8r-alertmanager:9093/api/v2"\n'
            'prometheusConfigServiceURL: "http://orc8r-prometheus:9100/v1"\n'
            'alertmanagerConfigServiceURL: "http://orc8r-alertmanager:9101/v1"\n'
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
        self._orc8r_base._container.push(f"{self.BASE_CONFIG_PATH}/metricsd.yml", metricsd_config)
        self._orc8r_base._container.push(f"{self.BASE_CONFIG_PATH}/analytics.yml", analytics_config)


if __name__ == "__main__":
    main(MagmaOrc8rAnalyticsCharm)
