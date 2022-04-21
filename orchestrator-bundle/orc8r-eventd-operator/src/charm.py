#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.
import logging
import re

from charms.magma_orc8r_libs.v0.orc8r_base import Orc8rBase
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus

logger = logging.getLogger(__name__)


class MagmaOrc8rEventdCharm(CharmBase):
    BASE_CONFIG_PATH = "/var/opt/magma/configs/orc8r"

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
        self.framework.observe(self.on.config_changed, self._on_elasticsearch_url_config_changed)

    def _on_elasticsearch_url_config_changed(self, event):
        # TODO: Elasticsearch url should be passed through a relationship (not a config)
        if self._elasticsearch_config_is_valid:
            if self._orc8r_base._container.can_connect():
                self._write_config_file()
                try:
                    logger.info("Restarting service")
                    self._orc8r_base._container.restart(self._orc8r_base._service_name)
                    self.unit.status = ActiveStatus()
                except RuntimeError:
                    logger.info("Service is not yet started, doing nothing")
                    pass
        else:
            self.unit.status = BlockedStatus(
                "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
            )

    def _write_config_file(self):
        logger.info("Writing config file or elastic.yml")
        elasticsearch_url, elasticsearch_port = self._get_elasticsearch_config()
        elastic_config = (
            f'"elasticHost": "{elasticsearch_url}"\n' f'"elasticPort": {elasticsearch_port}\n'
        )
        self._orc8r_base._container.push(f"{self.BASE_CONFIG_PATH}/elastic.yml", elastic_config)

    def _get_elasticsearch_config(self) -> tuple:
        elasticsearch_url = self.model.config.get("elasticsearch-url")
        elasticsearch_url_split = elasticsearch_url.split(":")
        return elasticsearch_url_split[0], elasticsearch_url_split[1]

    @property
    def _elasticsearch_config_is_valid(self) -> bool:
        elasticsearch_url = self.model.config.get("elasticsearch-url")
        if not elasticsearch_url:
            return False
        if re.match("^[a-zA-Z0-9._-]+:[0-9]+$", elasticsearch_url):
            return True
        else:
            return False


if __name__ == "__main__":
    main(MagmaOrc8rEventdCharm)
