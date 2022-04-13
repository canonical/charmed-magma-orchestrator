#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

from charms.magma_orc8r_libs.v0.orc8r_base import Orc8rBase
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from ops.charm import CharmBase
from ops.main import main


class MagmaOrc8rEventdCharm(CharmBase):
    BASE_CONFIG_PATH = "/var/opt/magma/configs/orc8r"

    # TODO: The various URL's should be provided through relationships
    ELASTICSEARCH_URL = "orc8r-elasticsearch"
    ELASTICSEARCH_PORT = 80

    def __init__(self, *args):
        """
        An instance of this object everytime an event occurs.
        """
        super().__init__(*args)
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[("grpc", 9180, 9121), ("http", 8080, 10121)],
            additional_labels={
                "app.kubernetes.io/part-of": "orc8r-app",
                "orc8r.io/obsidian_handlers": "true",
                "orc8r.io/swagger_spec": "true",
            },
            additional_annotations={
                "orc8r.io/obsidian_handlers_path_prefixes": "/magma/v1/networks/:network_id/logs, "
                "/magma/v1/events,"
            },
        )
        startup_command = (
            "/usr/bin/envdir "
            "/var/opt/magma/envdir "
            "/var/opt/magma/bin/eventd "
            "-run_echo_server=true "
            "-logtostderr=true "
            "-v=0"
        )
        self._orc8r_base = Orc8rBase(self, startup_command=startup_command)
        self.framework.observe(self.on.install, self._on_install)

    def _on_install(self, event):
        self._write_config_file()

    def _write_config_file(self):
        elastic_config = (
            f'"elasticHost": "{self.ELASTICSEARCH_URL}"\n'
            f'"elasticPort": {self.ELASTICSEARCH_PORT}\n'
        )
        self._orc8r_base._container.push(f"{self.BASE_CONFIG_PATH}/elastic.yml", elastic_config)


if __name__ == "__main__":
    main(MagmaOrc8rEventdCharm)
