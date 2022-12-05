#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import os
import re
from pathlib import Path
from typing import Union

from charms.observability_libs.v1.kubernetes_service_patch import (
    KubernetesServicePatch,
    ServicePort,
)
from jinja2 import Environment, FileSystemLoader
from ops.charm import CharmBase, ConfigChangedEvent, PebbleReadyEvent
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer

logger = logging.getLogger(__name__)


class FluentdElasticsearchCharm(CharmBase):

    CONFIG_DIRECTORY = "/etc/fluent/config.d"

    def __init__(self, *args):
        """An instance of this object everytime an event occurs."""
        super().__init__(*args)
        self._container_name = self._service_name = "fluentd"
        self._container = self.unit.get_container(self._container_name)
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[ServicePort(name="forward", port=24224)],
            service_type="LoadBalancer",
            service_name="fluentd",
        )

        self.framework.observe(self.on.fluentd_pebble_ready, self._configure)
        self.framework.observe(self.on.config_changed, self._configure)

    def _configure(self, event: Union[ConfigChangedEvent, PebbleReadyEvent]) -> None:
        """Configures fluentd once all prerequisites are in place.

        Args:
            event: Juju event (ConfigChangedEvent or PebbleReadyEvent)
        """
        if not self._elasticsearch_url_is_valid:
            self.unit.status = BlockedStatus(
                "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
            )
            return
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return
        self.unit.status = MaintenanceStatus("Configuring pod")
        self._write_config_files()
        self._configure_pebble_layer()
        self.unit.status = ActiveStatus()

    def _write_config_files(self) -> None:
        """Writes fluentd config files."""
        base_source_directory = os.path.join(
            os.path.abspath(os.path.dirname(__file__)),
            "config_files",
        )
        self._write_to_file(
            destination_path=Path(f"{self.CONFIG_DIRECTORY}/forward-input.conf"),
            content=self._read_file(Path(f"{base_source_directory}/forward-input.conf")),
        )
        self._write_to_file(
            destination_path=Path(f"{self.CONFIG_DIRECTORY}/general.conf"),
            content=self._read_file(Path(f"{base_source_directory}/general.conf")),
        )
        self._write_to_file(
            destination_path=Path(f"{self.CONFIG_DIRECTORY}/system.conf"),
            content=self._read_file(Path(f"{base_source_directory}/system.conf")),
        )
        self._write_to_file(
            destination_path=Path(f"{self.CONFIG_DIRECTORY}/output.conf"),
            content=self._render_config_file_template(
                Path(f"{base_source_directory}"), "output.conf.j2"
            ),
        )

    def _configure_pebble_layer(self) -> None:
        """Configures pebble layer."""
        pebble_layer = self._pebble_layer()
        plan = self._container.get_plan()
        if plan.services != pebble_layer.services:
            self._container.add_layer(self._container_name, pebble_layer, combine=True)
            self._container.restart(self._service_name)
            logger.info(f"Restarted container {self._service_name}")

    def _write_to_file(self, destination_path: Path, content: str) -> None:
        """Writes given content to a file in a given path.

        Args:
            destination_path (Path): Path of the destination file
            content (str): Content to put in the destination file
        """
        logger.info(f"Writing config file to {destination_path}")
        self._container.push(destination_path, content, permissions=0o777)

    def _pebble_layer(self) -> Layer:
        """Returns pebble layer for the charm.

        Returns:
            Layer: Pebble layer
        """
        return Layer(
            {
                "summary": "fluentd_elasticsearch layer",
                "description": "pebble config layer for fluentd_elasticsearch",
                "services": {
                    self._service_name: {
                        "override": "replace",
                        "summary": self._service_name,
                        "startup": "enabled",
                        "command": "./run.sh",
                    }
                },
            }
        )

    @staticmethod
    def _read_file(file: Path) -> str:
        """Reads given file's content.

        Args:
            file (Path): Path of the file to read

        Returns:
            str: Content of the file
        """
        with open(file, "r") as file:
            file_content = file.read()
        return file_content

    def _render_config_file_template(
        self, config_templates_dir: Path, template_file_name: str
    ) -> str:
        """Renders fluetnd config file from a given Jinja template.

        Args:
            config_templates_dir (Path): Directory containing config templates
            template_file_name (str): Template file name

        Returns:
            str: Rendered config file's content
        """
        file_loader = FileSystemLoader(config_templates_dir)
        env = Environment(loader=file_loader)
        template = env.get_template(template_file_name)
        elasticsearch_config = self._get_elasticsearch_config()
        fluentd_config = self._get_fluentd_config()
        return template.render(
            elasticsearch_host=elasticsearch_config["host"],
            elasticsearch_port=elasticsearch_config["port"],
            fluentd_chunk_limit_size=fluentd_config["chunk_limit_size"],
            fluentd_queue_limit_length=fluentd_config["queue_limit_length"],
        )

    def _get_elasticsearch_config(self) -> dict:
        """Extracts ElasticSearch configuration from Juju config.

        Returns:
            dict: ElasticSearch configuration
        """
        # TODO: Elasticsearch url and port should be passed through relationship
        elasticsearch_url = self.model.config.get("elasticsearch-url")
        elasticsearch_url_split = elasticsearch_url.split(":")  # type: ignore[union-attr]
        return {
            "host": elasticsearch_url_split[0],
            "port": elasticsearch_url_split[1],
        }

    def _get_fluentd_config(self) -> dict:
        """Extracts Fluentd configuration from Juju config.

        Returns:
            dict: Fluentd configuration
        """
        return {
            "chunk_limit_size": self.model.config.get("fluentd-chunk-limit-size"),
            "queue_limit_length": self.model.config.get("fluentd-queue-limit-length"),
        }

    @property
    def _elasticsearch_url_is_valid(self) -> bool:
        """Checks whether given Elasticsearch URL is valid or not.

        Returns:
            bool: True/False
        """
        elasticsearch_url = self.model.config.get("elasticsearch-url")
        if not elasticsearch_url:
            return False
        if re.match("^[a-zA-Z0-9._-]+:[0-9]+$", elasticsearch_url):
            return True
        else:
            return False


if __name__ == "__main__":
    main(FluentdElasticsearchCharm)
