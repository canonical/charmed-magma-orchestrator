#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import os
import re
from pathlib import Path
from typing import Optional, Union

from charms.magma_orc8r_certifier.v0.cert_certifier import CertCertifierRequires
from charms.magma_orc8r_certifier.v0.cert_certifier import (
    CertificateAvailableEvent as CertifierCertificateAvailableEvent,
)
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

    BASE_CERTS_PATH = "/certs"
    CONFIG_DIRECTORY = "/etc/fluent/config.d"
    REQUIRED_RELATIONS = ["cert-certifier"]

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
            additional_annotations={
                "external-dns.alpha.kubernetes.io/hostname": f"fluentd.{self._domain_config}"
            },
        )

        self.cert_certifier = CertCertifierRequires(charm=self, relationship_name="cert-certifier")

        self.framework.observe(self.on.fluentd_pebble_ready, self._configure)
        self.framework.observe(self.on.config_changed, self._configure)

        self.framework.observe(
            self.cert_certifier.on.certificate_available, self._on_certifier_certificate_available
        )

    def _configure(self, event: Union[ConfigChangedEvent, PebbleReadyEvent]) -> None:
        """Configures fluentd once all prerequisites are in place.

        Args:
            event: Juju event (ConfigChangedEvent or PebbleReadyEvent)
        """
        if not self._domain_config_is_valid:
            self.unit.status = BlockedStatus("Config 'domain' is not valid")
            event.defer()
            return
        if not self._elasticsearch_url_is_valid:
            self.unit.status = BlockedStatus(
                "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
            )
            return
        if not self._relations_created:
            event.defer()
            return
        if not self._certs_are_stored:
            self.unit.status = WaitingStatus("Waiting for certificates to be available")
            event.defer()
            return
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return
        self.unit.status = MaintenanceStatus("Configuring pod")
        self._write_config_files()
        self._configure_pebble_layer()
        self.unit.status = ActiveStatus()

    def _on_certifier_certificate_available(
        self, event: CertifierCertificateAvailableEvent
    ) -> None:
        """Saves certifier certificate to certs dir.

        Args:
            event: Juju event (CertifierCertificateAvailableEvent)
        """
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready...")
            event.defer()
            return
        self._container.push(
            f"{self.BASE_CERTS_PATH}/certifier.pem", event.certificate, permissions=0o420
        )

    def _write_config_files(self):
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

    def _write_to_file(self, destination_path: Path, content: str):
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
        with open(file, "r") as file:
            file_content = file.read()
        return file_content

    def _render_config_file_template(
        self, config_templates_dir: Path, template_file_name: str
    ) -> str:
        file_loader = FileSystemLoader(config_templates_dir)
        env = Environment(loader=file_loader)
        template = env.get_template(template_file_name)
        elasticsearch_config = self._get_elasticsearch_config()
        fluentd_config = self._get_fluentd_config()
        return template.render(
            domain=self._domain_config,
            elasticsearch_host=elasticsearch_config["host"],
            elasticsearch_port=elasticsearch_config["port"],
            elasticsearch_schema=elasticsearch_config["schema"],
            elasticsearch_ssl_version=elasticsearch_config["ssl_version"],
            fluentd_chunk_limit_size=fluentd_config["chunk_limit_size"],
            fluentd_queue_limit_length=fluentd_config["queue_limit_length"],
        )

    def _get_elasticsearch_config(self) -> dict:
        # TODO: Elasticsearch url and port should be passed through relationship
        elasticsearch_url = self.model.config.get("elasticsearch-url")
        elasticsearch_url_split = elasticsearch_url.split(":")  # type: ignore[union-attr]
        return {
            "host": elasticsearch_url_split[0],
            "port": elasticsearch_url_split[1],
            "schema": self.model.config.get("elasticsearch-schema"),
            "ssl_version": self.model.config.get("elasticsearch-ssl-version"),
        }

    def _get_fluentd_config(self) -> dict:
        return {
            "chunk_limit_size": self.model.config.get("fluentd-chunk-limit-size"),
            "queue_limit_length": self.model.config.get("fluentd-queue-limit-length"),
        }

    @property
    def _domain_config_is_valid(self) -> bool:
        """Returns whether the "domain" config is valid.

        Returns:
            bool: Whether the domain is a valid one.
        """
        if not self._domain_config:
            return False
        pattern = re.compile(
            r"^(?:[a-zA-Z0-9]"  # First character of the domain
            r"(?:[a-zA-Z0-9-_]{0,61}[A-Za-z0-9])?\.)"  # Sub domain + hostname
            r"+[A-Za-z0-9][A-Za-z0-9-_]{0,61}"  # First 61 characters of the gTLD
            r"[A-Za-z]$"  # Last character of the gTLD
        )
        if pattern.match(self._domain_config):
            return True
        return False

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

    @property
    def _relations_created(self) -> bool:
        """Checks whether required relations are created.

        Returns:
            bool: True/False
        """
        if missing_relations := [
            relation
            for relation in self.REQUIRED_RELATIONS
            if not self.model.get_relation(relation)
        ]:
            msg = f"Waiting for relation(s) to be created: {', '.join(missing_relations)}"
            self.unit.status = BlockedStatus(msg)
            return False
        return True

    @property
    def _certs_are_stored(self) -> bool:
        """Checks whether the required certs are stored in the container.

        Returns:
            bool: True/False
        """
        if not self._container.can_connect():
            return False
        return all(
            [
                self._cert_is_stored(f"{self.BASE_CERTS_PATH}/certifier.pem"),
                # TODO: Placeholder for fluentd certs
            ]
        )

    @property
    def _domain_config(self) -> Optional[str]:
        """Returns domain config."""
        return self.model.config.get("domain")

    def _cert_is_stored(self, cert_path: str) -> bool:
        """Checks whether given cert is stored in the container.

        Args:
            cert_path (str): Certificate path

        Returns:
            bool: True/False
        """
        return self._container.exists(cert_path)


if __name__ == "__main__":
    main(FluentdElasticsearchCharm)
