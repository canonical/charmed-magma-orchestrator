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
from ops.charm import CharmBase, ConfigChangedEvent, InstallEvent, RelationJoinedEvent
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer

logger = logging.getLogger(__name__)


class FluentdElasticsearchCharm(CharmBase):

    CERTIFICATES_DIRECTORY = "/certs"
    CONFIG_SOURCE_DIRECTORY = os.path.join(
        os.path.abspath(os.path.dirname(__file__)),
        "config_files",
    )
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
        )
        self._fluentd_certificates = TLSCertificatesRequiresV1(self, "fluentd-certs")

        self.framework.observe(self.on.install, self._on_install)
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

    def _on_install(self, event: InstallEvent) -> None:
        """Handles Fluentd's one time configuration tasks.

        Writes Fluentd static configs to the container.

        Args:
            event: Juju event (InstallEvent)
        """
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return
        self.unit.status = MaintenanceStatus("Configuring pod")
        self._write_static_config_files()

    def _configure(
        self, event: Union[CertificateAvailableEvent, ConfigChangedEvent]
    ) -> None:
        """Configures fluentd once all prerequisites are in place.

        Args:
            event: Juju event (PebbleReadyEvent)
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
        self._write_dynamic_config_files()
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

    def _write_static_config_files(self) -> None:
        """Writes static Fluentd config files to the container."""
        self._write_to_file(
            destination_path=Path(f"{self.CONFIG_DIRECTORY}/forward-input.conf"),
            content=self._read_file(Path(f"{self.CONFIG_SOURCE_DIRECTORY}/forward-input.conf")),
        )
        self._write_to_file(
            destination_path=Path(f"{self.CONFIG_DIRECTORY}/general.conf"),
            content=self._read_file(Path(f"{self.CONFIG_SOURCE_DIRECTORY}/general.conf")),
        )
        self._write_to_file(
            destination_path=Path(f"{self.CONFIG_DIRECTORY}/system.conf"),
            content=self._read_file(Path(f"{self.CONFIG_SOURCE_DIRECTORY}/system.conf")),
        )

    def _write_dynamic_config_files(self) -> None:
        """Writes dynamic Fluentd config files to the container."""
        self._write_to_file(
            destination_path=Path(f"{self.CONFIG_DIRECTORY}/output.conf"),
            content=self._render_config_file_template(
                Path(f"{self.CONFIG_SOURCE_DIRECTORY}"), "output.conf.j2"
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
        return template.render(
            elasticsearch_host=self._elasticsearch_host,
            elasticsearch_port=self._elasticsearch_port,
            elasticsearch_scheme="https",
            fluentd_chunk_limit_size=self._config_fluentd_chunk_limit_size,
            fluentd_queue_limit_length=self._config_fluentd_queue_limit_length,
        )

    @property
    def _elasticsearch_host(self) -> Optional[str]:
        """Returns ElasticSearch hostname extracted from elasticsearch-url config param.

        Returns:
            str: ElasticSearch hostname
        """
        elasticsearch_url = self.model.config.get("elasticsearch-url")
        if elasticsearch_url:
            return elasticsearch_url.split(":")[0]
        else:
            return None

    @property
    def _elasticsearch_port(self) -> Optional[str]:
        """Returns ElasticSearch port extracted from elasticsearch-url config param.

        Returns:
            str: ElasticSearch hostname
        """
        elasticsearch_url = self.model.config.get("elasticsearch-url")
        if elasticsearch_url:
            return elasticsearch_url.split(":")[1]
        else:
            return None

    @property
    def _config_fluentd_chunk_limit_size(self) -> Optional[str]:
        """Return the value of fluentd-chunk-limit-size config param.

        Returns:
            str: fluentd-chunk-limit-size value
        """
        return self.model.config.get("fluentd-chunk-limit-size")

    @property
    def _config_fluentd_queue_limit_length(self) -> Optional[str]:
        """Return the value of fluentd-queue-limit-length config param.

        Returns:
            str: fluentd-queue-limit-length
        """
        return self.model.config.get("fluentd-queue-limit-length")

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
        """Returns whether given Elasticsearch URL is valid or not.

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
