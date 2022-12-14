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
    CertificateExpiredEvent,
    CertificateExpiringEvent,
    CertificateRevokedEvent,
    TLSCertificatesRequiresV1,
    generate_csr,
    generate_private_key,
)
from cryptography import x509
from jinja2 import Environment, FileSystemLoader
from ops.charm import CharmBase, ConfigChangedEvent, InstallEvent
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
            self._fluentd_certificates.on.certificate_available,
            self._on_fluentd_certificates_available,
        )
        self.framework.observe(
            self._fluentd_certificates.on.certificate_expiring, self._on_certificate_renewal_needed
        )
        self.framework.observe(
            self._fluentd_certificates.on.certificate_expired, self._on_certificate_renewal_needed
        )
        self.framework.observe(
            self._fluentd_certificates.on.certificate_revoked, self._on_certificate_renewal_needed
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

    def _configure(self, event: Union[CertificateAvailableEvent, ConfigChangedEvent]) -> None:
        """Configures fluentd once all prerequisites are in place.

        Args:
            event: Juju event (PebbleReadyEvent)
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
        if not self._peer_relation_created:
            self.unit.status = WaitingStatus("Waiting for replicas relation to be created")
            event.defer()
            return
        if not self._fluentd_certs_relation_created:
            self.unit.status = BlockedStatus("Waiting for fluentd-certs relation to be created")
            event.defer()
            return
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for the container to be available")
            event.defer()
            return
        if self.unit.is_leader():
            self._request_fluentd_certificates()
        else:
            if not self._fluentd_private_key_stored_in_peer_relation_data:
                self.unit.status = WaitingStatus("Waiting for Fluentd private key to be available")
                event.defer()
                return
            if not self._fluentd_csr_stored_in_peer_relation_data:
                self.unit.status = WaitingStatus("Waiting for Fluentd CSR to be available")
                event.defer()
                return
        if not self._fluentd_certificates_stored_in_peer_relation_data:
            self.unit.status = WaitingStatus("Waiting for Fluentd certificates to be available")
            event.defer()
            return
        self.unit.status = MaintenanceStatus("Configuring pod")
        self._save_fluentd_private_key_to_file(self._fluentd_private_key)
        self._save_fluentd_csr_to_file(self._fluentd_csr)
        self._save_fluentd_cert_to_file(self._get_value_from_peer_relation_data("fluentd_cert"))
        self._save_ca_cert_to_file(self._get_value_from_peer_relation_data("ca_cert"))
        self._write_dynamic_config_files()
        self._configure_pebble_layer()
        self.unit.status = ActiveStatus()

    def _on_fluentd_certificates_available(self, event: CertificateAvailableEvent) -> None:
        """Saves Fluentd certificate and CA certificate to the container.

        Args:
            event: Juju event (CertificateAvailableEvent)
        """
        if not self._peer_relation_created:
            self.unit.status = WaitingStatus("Waiting for replicas relation to be created")
            event.defer()
            return
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for the container to be available")
            event.defer()
            return
        self._push_fluentd_cert_to_peer_relation_data(event.certificate)
        self._push_ca_cert_to_peer_relation_data(event.ca)
        self._configure(event)

    def _on_certificate_renewal_needed(
        self,
        event: Union[CertificateExpiringEvent, CertificateExpiredEvent, CertificateRevokedEvent],
    ) -> None:
        """Triggered whenever new Fluentd certificate is needed.

        Will ask for new certificates.

        Args:
            event: Juju event
        """
        if not self.unit.is_leader():
            return
        if not self._domain_config_is_valid:
            self.unit.status = BlockedStatus("Config 'domain' is not valid")
            return
        if not self._fluentd_private_key_stored_in_peer_relation_data:
            self._request_certificate_based_on_new_private_key()
            return
        if not self._fluentd_csr_stored_in_peer_relation_data:
            self._request_certificate_based_on_existing_private_key()
            return
        self._renew_cerificate()
        self.unit.status = WaitingStatus("Waiting to receive new certificate from provider")

    def _request_fluentd_certificates(self) -> None:
        """Requests Fluentd certificates."""
        if not self._fluentd_private_key_stored_in_peer_relation_data:
            self._request_certificate_based_on_new_private_key()
            return
        if not self._fluentd_csr_stored_in_peer_relation_data:
            self._request_certificate_based_on_existing_private_key()
            return
        if not self._stored_csr_matches_charm_config:
            self._renew_cerificate()
            return

    def _request_certificate_based_on_new_private_key(self) -> None:
        """Does the whole path of getting an SSL certificate for Fluentd.

        Generates a private key.
        Generates a CSR.
        Requests a Fluentd certificate.
        """
        self._generate_and_save_fluentd_private_key()
        self._request_certificate_based_on_existing_private_key()

    def _request_certificate_based_on_existing_private_key(self) -> None:
        """Gets Fluentd certificate based on existing private key.

        Generates CSR.
        Requests a Fluentd certificate.
        """
        self._generate_and_save_fluentd_csr()
        self._fluentd_certificates.request_certificate_creation(self._fluentd_csr.encode())

    def _renew_cerificate(self) -> None:
        """Renews Fluentd certificate.

        Generates new CSR based on existing private key.
        Requests Fluentd certificate renewal from the provider.
        """
        old_csr = self._fluentd_csr
        self._generate_and_save_fluentd_csr()
        self._fluentd_certificates.request_certificate_renewal(
            old_certificate_signing_request=old_csr.encode(),
            new_certificate_signing_request=self._fluentd_csr.encode(),
        )

    def _generate_and_save_fluentd_private_key(self) -> None:
        """Generates Fluentd private key and saves it in the peer relation data."""
        fluentd_private_key = generate_private_key()
        self._store_item_in_peer_relation_data("fluentd_private_key", fluentd_private_key.decode())

    def _generate_and_save_fluentd_csr(self) -> None:
        """Generates Fluentd CSR and saves it in the peer relation data."""
        if not self._fluentd_private_key_stored_in_peer_relation_data:
            raise RuntimeError("Fluentd private key not available")
        fluentd_csr = generate_csr(
            private_key=self._fluentd_private_key.encode(),
            subject=f"fluentd.{self._domain_config}",
        )
        self._store_item_in_peer_relation_data("fluentd_csr", fluentd_csr.decode())

    def _push_fluentd_cert_to_peer_relation_data(self, fluentd_cert: str) -> None:
        """Pushes Fluentd certificate to peer relation data.

        Args:
            fluentd_cert (str): Fluentd certificate
        """
        if not self._peer_relation_created:
            raise RuntimeError("No peer relation")
        self._store_item_in_peer_relation_data("fluentd_cert", fluentd_cert)

    def _push_ca_cert_to_peer_relation_data(self, ca_cert: str) -> None:
        """Pushes CA certificate to peer relation data.

        Args:
            ca_cert (str): Fluentd certificate
        """
        if not self._peer_relation_created:
            raise RuntimeError("No peer relation")
        self._store_item_in_peer_relation_data("ca_cert", ca_cert)

    def _save_fluentd_private_key_to_file(self, private_key: Optional[str]) -> None:
        """Saves Fluentd private key to a file.

        Args:
            private_key (str): Fluentd private key
        """
        self._write_to_file(
            destination_path=Path(f"{self.CERTIFICATES_DIRECTORY}/fluentd.key"),
            content=private_key,
            permissions=0o420,
        )

    def _save_fluentd_csr_to_file(self, csr: Optional[str]) -> None:
        """Saves Fluentd CSR to a file.

        Args:
            csr (str): Fluentd CSR
        """
        self._write_to_file(
            destination_path=Path(f"{self.CERTIFICATES_DIRECTORY}/fluentd.csr"),
            content=csr,
            permissions=0o420,
        )

    def _save_fluentd_cert_to_file(self, cert: Optional[str]) -> None:
        """Saves Fluentd certificate to a file.

        Args:
            cert (str): Fluentd certificate
        """
        self._write_to_file(
            destination_path=Path(f"{self.CERTIFICATES_DIRECTORY}/fluentd.pem"),
            content=cert,
            permissions=0o420,
        )

    def _save_ca_cert_to_file(self, cert: Optional[str]) -> None:
        """Saves CA certificate to a file.

        Args:
            cert (str): CA certificate
        """
        self._write_to_file(
            destination_path=Path(f"{self.CERTIFICATES_DIRECTORY}/ca.pem"),
            content=cert,
            permissions=0o420,
        )

    @property
    def _fluentd_private_key(self) -> str:
        """Returns Fluentd private key.

        Returns:
            str: Fluentd private key
        """
        return self._get_value_from_peer_relation_data("fluentd_private_key") or ""

    @property
    def _fluentd_csr(self) -> str:
        """Returns Fluentd CSR.

        Returns:
            str: Fluentd CSR
        """
        return self._get_value_from_peer_relation_data("fluentd_csr") or ""

    @property
    def _fluentd_private_key_stored_in_peer_relation_data(self) -> bool:
        """Returns whether Fluentd private key is stored in the peer relation data.

        Returns:
            bool: Whether Fluentd private key is stored in the peer relation data.
        """
        return bool(self._fluentd_private_key)

    @property
    def _fluentd_csr_stored_in_peer_relation_data(self) -> bool:
        """Returns whether Fluentd CSR is stored in the peer relation data.

        Returns:
            bool: Whether Fluentd CSR is stored in the peer relation data.
        """
        return bool(self._fluentd_csr)

    @property
    def _fluentd_certificates_stored_in_peer_relation_data(self) -> bool:
        """Checks whether the required certs are stored in the peer relation data.

        Returns:
            bool: Whether the required certs are stored in the peer relation data.
        """
        return all(
            [
                self._get_value_from_peer_relation_data("fluentd_cert"),
                self._get_value_from_peer_relation_data("ca_cert"),
            ]
        )

    def _write_static_config_files(self) -> None:
        """Writes static Fluentd config files to the container."""
        self._write_to_file(
            destination_path=Path(f"{self.CONFIG_DIRECTORY}/forward-input.conf"),
            content=self._read_file(Path(f"{self.CONFIG_SOURCE_DIRECTORY}/forward-input.conf")),
            permissions=0o666,
        )
        self._write_to_file(
            destination_path=Path(f"{self.CONFIG_DIRECTORY}/general.conf"),
            content=self._read_file(Path(f"{self.CONFIG_SOURCE_DIRECTORY}/general.conf")),
            permissions=0o666,
        )
        self._write_to_file(
            destination_path=Path(f"{self.CONFIG_DIRECTORY}/system.conf"),
            content=self._read_file(Path(f"{self.CONFIG_SOURCE_DIRECTORY}/system.conf")),
            permissions=0o666,
        )

    def _write_dynamic_config_files(self) -> None:
        """Writes dynamic Fluentd config files to the container."""
        self._write_to_file(
            destination_path=Path(f"{self.CONFIG_DIRECTORY}/output.conf"),
            content=self._render_config_file_template(
                Path(f"{self.CONFIG_SOURCE_DIRECTORY}"), "output.conf.j2"
            ),
            permissions=0o666,
        )

    def _configure_pebble_layer(self) -> None:
        """Configures pebble layer."""
        pebble_layer = self._pebble_layer()
        plan = self._container.get_plan()
        if plan.services != pebble_layer.services:
            self._container.add_layer(self._container_name, pebble_layer, combine=True)
            self._container.restart(self._service_name)
            logger.info(f"Restarted container {self._service_name}")

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

    @property
    def _stored_csr_matches_charm_config(self) -> bool:
        """Returns whether the stored CSR matches charm's config.

        Returns:
            bool: Whether the stored CSR matches charm's config.
        """
        if not self._fluentd_csr:
            raise RuntimeError("Fluentd CSR not available")
        csr_object = x509.load_pem_x509_csr(data=self._fluentd_csr.encode())
        if f"fluentd.{self._domain_config}" == list(csr_object.subject)[0].value:
            return True
        else:
            logger.info("Fluentd CSR subject doesn't match charm's config")
            return False

    def _write_to_file(
        self, destination_path: Path, content: Optional[str], permissions: Optional[int]
    ) -> None:
        """Writes given content to a file in a given path.

        Args:
            destination_path (Path): Path of the destination file
            content (str): Content to put in the destination file
            permissions (int): File permissions
        """
        if not content:
            raise RuntimeError("Can't write to file - content not available")
        self._container.push(destination_path, content, permissions=permissions)
        logger.info(f"Config file written to {destination_path}")

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
        return bool(pattern.match(self._domain_config))

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

    def _store_item_in_peer_relation_data(self, key: str, value: str) -> None:
        """Stores key/value in peer relation data.

        Args:
            key (str): Relation data key
            value (str): Relation data value

        Returns:
            None
        """
        peer_relation = self.model.get_relation("replicas")
        if not peer_relation:
            raise RuntimeError("No peer relation")
        peer_relation.data[self.app].update({key: value.strip()})

    def _get_value_from_peer_relation_data(self, key: str) -> Optional[str]:
        """Returns value from peer relation data.

        Args:
            key (str): Relation data key

        Returns:
            Optional[str]: Relation data value
        """
        replicas = self.model.get_relation("replicas")
        if not replicas:
            return None
        relation_data = replicas.data[self.app].get(key, None)
        if relation_data:
            return relation_data.strip()
        else:
            return None

    @property
    def _peer_relation_created(self) -> bool:
        """Returns whether the replicas relation is created.

        Returns:
            bool: Whether the replicas relation is created.
        """
        return self._relation_created("replicas")

    @property
    def _fluentd_certs_relation_created(self) -> bool:
        """Checks whether the fluentd-certs relation is created.

        Returns:
            bool: Whether the fluentd-certs relation is created.
        """
        return self._relation_created("fluentd-certs")

    def _relation_created(self, relation_name: str) -> bool:
        """Returns whether a given Juju relation was crated.

        Args:
            relation_name (str): Relation name

        Returns:
            str: Whether the relation was created.
        """
        return bool(self.model.get_relation(relation_name))

    @property
    def _domain_config(self) -> Optional[str]:
        """Returns domain config.

        Returns:
            str: Domain
        """
        return self.model.config.get("domain")


if __name__ == "__main__":
    main(FluentdElasticsearchCharm)
