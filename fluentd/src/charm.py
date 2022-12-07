#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import os
import re
from pathlib import Path
from typing import Optional, Union

from charms.observability_libs.v1.kubernetes_service_patch import (
    KubernetesServicePatch,
    ServicePort,
)
from charms.tls_certificates_interface.v1.tls_certificates import (
    CertificateAvailableEvent,
    CertificateExpiringEvent,
    CertificateRevokedEvent,
    TLSCertificatesRequiresV1,
    generate_csr,
    generate_private_key,
)
from jinja2 import Environment, FileSystemLoader
from ops.charm import CharmBase, ConfigChangedEvent, PebbleReadyEvent, RelationJoinedEvent
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer

logger = logging.getLogger(__name__)


class FluentdElasticsearchCharm(CharmBase):

    CERTIFICATES_DIRECTORY = "/certs"
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
        self._fluentd_certificates = TLSCertificatesRequiresV1(self, "fluentd-certs")

        self.framework.observe(self.on.fluentd_pebble_ready, self._configure)
        self.framework.observe(self.on.config_changed, self._configure)
        self.framework.observe(
            self.on.fluentd_certs_relation_joined, self._on_fluentd_certs_relation_joined
        )

        self.framework.observe(
            self._fluentd_certificates.on.certificate_available,
            self._on_fluentd_certificates_available,
        )
        self.framework.observe(
            self._fluentd_certificates.on.certificate_expiring, self._on_certificate_expiring
        )
        self.framework.observe(
            self._fluentd_certificates.on.certificate_expired, self._on_certificate_expiring
        )

    def _configure(
        self, event: Union[CertificateAvailableEvent, ConfigChangedEvent, PebbleReadyEvent]
    ) -> None:
        """Configures fluentd once all prerequisites are in place.

        Args:
            event: Juju event (ConfigChangedEvent or PebbleReadyEvent)
        """
        if not self._elasticsearch_url_is_valid:
            self.unit.status = BlockedStatus(
                "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
            )
            return
        if not self._fluentd_certs_relation_created:
            self.unit.status = BlockedStatus("Waiting for fluentd-certs relation to be created")
            event.defer()
            return
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for the container to be available")
            event.defer()
            return
        if not self._fluentd_certificates_are_stored:
            self.unit.status = WaitingStatus("Waiting for Fluentd certificates to be available")
            event.defer()
            return
        self.unit.status = MaintenanceStatus("Configuring pod")
        self._write_config_files()
        self._configure_pebble_layer()
        self.unit.status = ActiveStatus()

    def _on_fluentd_certs_relation_joined(self, event: RelationJoinedEvent) -> None:
        """Runs whenever fluentd-certs relation joins.

        Generates Fluentd CSR and private key and saves them in the container.
        Requests Fluentd certificates using CSR.

        Args:
            event: Juju event (RelationJoinedEvent)
        """
        if not self.unit.is_leader():
            return
        if not self._domain_config_is_valid:
            self.unit.status = BlockedStatus("Config 'domain' is not valid")
            event.defer()
            return
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for the container to be available")
            event.defer()
            return
        self._generate_and_save_fluentd_private_key()
        self._generate_and_save_fluentd_csr()
        self._fluentd_certificates.request_certificate_creation(self._fluetnd_csr)

    def _on_fluentd_certificates_available(self, event: CertificateAvailableEvent) -> None:
        """Saves Fluentd certificate and CA certificate to the container.

        Args:
            event: Juju event (CertificateAvailableEvent)
        """
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for the container to be available")
            event.defer()
            return
        self._write_to_file(
            destination_path=Path(f"{self.CERTIFICATES_DIRECTORY}/ca.pem"),
            content=event.ca,
            permissions=0o420,
        )
        self._write_to_file(
            destination_path=Path(f"{self.CERTIFICATES_DIRECTORY}/fluentd.pem"),
            content=event.certificate,
            permissions=0o420,
        )
        self._configure(event)

    def _generate_and_save_fluentd_private_key(self) -> None:
        """Generates Fluentd private key and saves it in the container."""
        fluentd_private_key = generate_private_key()
        self._write_to_file(
            destination_path=Path(f"{self.CERTIFICATES_DIRECTORY}/fluentd.key"),
            content=fluentd_private_key.decode(),
            permissions=0o420,
        )

    def _generate_and_save_fluentd_csr(self) -> None:
        """Generates Fluentd CSR and saves it in the container."""
        fluentd_csr = generate_csr(
            private_key=self._fluentd_private_key, subject=f"fluentd.{self._domain_config}"
        )
        self._write_to_file(
            destination_path=Path(f"{self.CERTIFICATES_DIRECTORY}/fluentd.csr"),
            content=fluentd_csr.decode(),
            permissions=0o420,
        )

    @property
    def _fluentd_private_key(self) -> bytes:
        """Returns Fluentd private key.

        Returns:
            bytes: Fluentd private key
        """
        return self._container.pull(Path(f"{self.CERTIFICATES_DIRECTORY}/fluentd.key")).read()

    @property
    def _fluetnd_csr(self) -> bytes:
        """Returns Fluentd CSR.

        Returns:
            bytes: Fluentd CSR
        """
        return self._container.pull(Path(f"{self.CERTIFICATES_DIRECTORY}/fluentd.csr")).read()

    def _write_config_files(self) -> None:
        """Writes fluentd config files."""
        base_source_directory = os.path.join(
            os.path.abspath(os.path.dirname(__file__)),
            "config_files",
        )
        self._write_to_file(
            destination_path=Path(f"{self.CONFIG_DIRECTORY}/forward-input.conf"),
            content=self._read_file(Path(f"{base_source_directory}/forward-input.conf")),
            permissions=0o777,
        )
        self._write_to_file(
            destination_path=Path(f"{self.CONFIG_DIRECTORY}/general.conf"),
            content=self._read_file(Path(f"{base_source_directory}/general.conf")),
            permissions=0o777,
        )
        self._write_to_file(
            destination_path=Path(f"{self.CONFIG_DIRECTORY}/system.conf"),
            content=self._read_file(Path(f"{base_source_directory}/system.conf")),
            permissions=0o777,
        )
        self._write_to_file(
            destination_path=Path(f"{self.CONFIG_DIRECTORY}/output.conf"),
            content=self._render_config_file_template(
                Path(f"{base_source_directory}"), "output.conf.j2"
            ),
            permissions=0o777,
        )

    def _configure_pebble_layer(self) -> None:
        """Configures pebble layer."""
        pebble_layer = self._pebble_layer()
        plan = self._container.get_plan()
        if plan.services != pebble_layer.services:
            self._container.add_layer(self._container_name, pebble_layer, combine=True)
            self._container.restart(self._service_name)
            logger.info(f"Restarted container {self._service_name}")

    @property
    def _fluentd_certificates_are_stored(self) -> bool:
        """Checks whether the required certs are stored in the container.

        Returns:
            bool: True/False
        """
        if not self._container.can_connect():
            return False
        return all(
            [
                self._file_is_stored(f"{self.CERTIFICATES_DIRECTORY}/ca.pem"),
                self._file_is_stored(f"{self.CERTIFICATES_DIRECTORY}/fluentd.key"),
                self._file_is_stored(f"{self.CERTIFICATES_DIRECTORY}/fluentd.pem"),
            ]
        )

    def _write_to_file(self, destination_path: Path, content: str, permissions: int) -> None:
        """Writes given content to a file in a given path.

        Args:
            destination_path (Path): Path of the destination file
            content (str): Content to put in the destination file
            permissions (int): File permissions
        """
        logger.info(f"Writing config file to {destination_path}")
        self._container.push(destination_path, content, permissions=permissions)

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
            elasticsearch_scheme="https",
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
    def _fluentd_certs_relation_created(self) -> bool:
        """Checks whether fluentd-certs relation is created.

        Returns:
            bool: True/False
        """
        if not self.model.get_relation("fluentd-certs"):
            return False
        return True

    def _file_is_stored(self, file_path: str) -> bool:
        """Checks whether given file is stored in the container.

        Args:
            file_path (str): File path

        Returns:
            bool: True/False
        """
        return self._container.exists(file_path)

    @property
    def _domain_config(self) -> Optional[str]:
        """Returns domain config.

        Returns:
            str: Domain
        """
        return self.model.config.get("domain")


if __name__ == "__main__":
    main(FluentdElasticsearchCharm)
