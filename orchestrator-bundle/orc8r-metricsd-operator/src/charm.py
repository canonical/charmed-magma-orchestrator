#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

from charms.magma_orc8r_libs.v0.orc8r_base import Orc8rBase
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from ops.charm import CharmBase, InstallEvent
from ops.main import main

logger = logging.getLogger(__name__)


class MagmaOrc8rMetricsdCharm(CharmBase):

    BASE_CONFIG_PATH = "/var/opt/magma/configs/orc8r"

    # TODO: The various URL's should be provided through relationships.
    PROMETHEUS_URL = "http://orc8r-prometheus:9090"
    PROMETHEUS_CONFIGURER_URL = "http://orc8r-prometheus:9100"
    ALERTMANAGER_URL = "http://orc8r-alertmanager:9093"
    ALERTMANAGER_CONFIGURER_URL = "http://orc8r-alertmanager:9101"

    def __init__(self, *args):
        """
        An instance of this object everytime an event occurs.
        """
        super().__init__(*args)
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[("grpc", 9180, 9084), ("http", 8080, 10084)],
            additional_labels={
                "app.kubernetes.io/part-of": "orc8r-app",
                "orc8r.io/obsidian_handlers": "true",
                "orc8r.io/swagger_spec": "true",
            },
            additional_annotations={
                "orc8r.io/obsidian_handlers_path_prefixes": "/magma/v1/networks/:network_id/alerts, "  # noqa: E501
                "/magma/v1/networks/:network_id/metrics, "
                "/magma/v1/networks/:network_id/prometheus, "
                "/magma/v1/tenants/:tenant_id/metrics, "
                "/magma/v1/tenants/targets_metadata,"
            },
        )
        startup_command = (
            "/usr/bin/envdir "
            "/var/opt/magma/envdir "
            "/var/opt/magma/bin/metricsd "
            "-run_echo_server=true "
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
            f'prometheusConfigServiceURL: "{self.PROMETHEUS_CONFIGURER_URL}/v1"\n'
            f'alertmanagerConfigServiceURL: "{self.ALERTMANAGER_CONFIGURER_URL}/v1"\n'
            '"profile": "prometheus"\n'
        )
        self._orc8r_base.container.push(f"{self.BASE_CONFIG_PATH}/metricsd.yml", metricsd_config)

    @property
    def _namespace(self) -> str:
        return self.model.name


if __name__ == "__main__":
    main(MagmaOrc8rMetricsdCharm)
