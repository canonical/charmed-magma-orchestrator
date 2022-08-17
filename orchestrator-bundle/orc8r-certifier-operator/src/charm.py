#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Maintains and verifies signed client certificates and their associated identities."""

import base64
import logging
import re
import secrets
import string
from typing import Optional, Union

import ops.lib
import psycopg2  # type: ignore[import]
from charms.magma_orc8r_certifier.v0.cert_admin_operator import (
    CertAdminOperatorProvides,
)
from charms.magma_orc8r_certifier.v0.cert_admin_operator import (
    CertificateRequestEvent as AdminOperatorCertificateRequestEvent,
)
from charms.magma_orc8r_certifier.v0.cert_certifier import CertCertifierProvides
from charms.magma_orc8r_certifier.v0.cert_certifier import (
    CertificateRequestEvent as CertifierCertificateRequestEvent,
)
from charms.magma_orc8r_certifier.v0.cert_controller import CertControllerProvides
from charms.magma_orc8r_certifier.v0.cert_controller import (
    CertificateRequestEvent as ControllerCertificateRequestEvent,
)
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
    generate_ca,
    generate_certificate,
    generate_csr,
    generate_pfx_package,
    generate_private_key,
)
from cryptography import x509
from ops.charm import (
    ActionEvent,
    CharmBase,
    ConfigChangedEvent,
    InstallEvent,
    PebbleReadyEvent,
    RelationJoinedEvent,
)
from ops.main import main
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
    ModelError,
    Relation,
    WaitingStatus,
)
from ops.pebble import Layer
from pgconnstr import ConnectionString  # type: ignore[import]

logger = logging.getLogger(__name__)
pgsql = ops.lib.use("pgsql", 1, "postgresql-charmers@lists.launchpad.net")


class MagmaOrc8rCertifierCharm(CharmBase):
    """Main class that is instantiated everytime an event occurs."""

    DB_NAME = "magma_dev"
    BASE_CONFIG_PATH = "/var/opt/magma/configs/orc8r"
    BASE_CERTIFICATES_PATH = "/var/opt/magma/certs"

    # TODO: The various URL's should be provided through relationships
    PROMETHEUS_URL = "http://orc8r-prometheus:9090"
    ALERTMANAGER_URL = "http://orc8r-alertmanager:9093"

    def __init__(self, *args):
        """Initializes all events that need to be observed."""
        super().__init__(*args)
        self.tls_certificates_requirer = TLSCertificatesRequiresV1(self, "certificates")
        self.certificates_admin_operator_provider = CertAdminOperatorProvides(
            self, "cert-admin-operator"
        )
        self.certificates_certifier_provider = CertCertifierProvides(self, "cert-certifier")
        self.certificates_controller_provider = CertControllerProvides(self, "cert-controller")
        self._container_name = self._service_name = "magma-orc8r-certifier"
        self.provided_relation_name = list(self.meta.provides.keys())[0]
        self._container = self.unit.get_container(self._container_name)
        self._db = pgsql.PostgreSQLClient(self, "db")
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[ServicePort(name="grpc", port=9180, targetPort=9086)],
            additional_labels={
                "app.kubernetes.io/part-of": "orc8r-app",
                "orc8r.io/analytics_collector": "true",
            },
        )
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(
            self.tls_certificates_requirer.on.certificate_available, self._on_certificate_available
        )
        self.framework.observe(
            self.tls_certificates_requirer.on.certificate_expiring, self._on_certificate_expiring
        )
        self.framework.observe(
            self.tls_certificates_requirer.on.certificate_expired, self._on_certificate_expiring
        )
        self.framework.observe(
            self.tls_certificates_requirer.on.certificate_revoked, self._on_certificate_expiring
        )
        self.framework.observe(
            self.on.certificates_relation_created, self._on_certificates_relation_created
        )
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(
            self.on.magma_orc8r_certifier_pebble_ready, self._on_magma_orc8r_certifier_pebble_ready
        )
        self.framework.observe(
            self._db.on.database_relation_joined, self._on_database_relation_joined
        )
        self.framework.observe(
            self.on.get_pfx_package_password_action, self._on_get_pfx_package_password
        )
        self.framework.observe(
            self.certificates_admin_operator_provider.on.certificate_request,
            self._on_admin_operator_certificate_request,
        )
        self.framework.observe(
            self.certificates_certifier_provider.on.certificate_request,
            self._on_certifier_certificate_request,
        )
        self.framework.observe(
            self.certificates_controller_provider.on.certificate_request,
            self._on_controller_certificate_request,
        )

    @property
    def _root_certificates_are_pushed(self) -> bool:
        """Returns whether root certificate are pushed to workload.

        Returns:
            bool: Whether root certificate are pushed to workload.
        """
        if not self._container.exists(f"{self.BASE_CERTIFICATES_PATH}/controller.crt"):
            logger.info("Root certificate is not pushed")
            return False
        if not self._container.exists(f"{self.BASE_CERTIFICATES_PATH}/rootCA.pem"):
            logger.info("Root CA Certificate is not pushed")
            return False
        return True

    @property
    def _root_private_key_is_pushed(self) -> bool:
        """Returns whether root private key is pushed to workload.

        Returns:
            bool: True/False
        """
        if not self._container.exists(f"{self.BASE_CERTIFICATES_PATH}/controller.key"):
            logger.info("Root private key is not pushed")
            return False
        return True

    @property
    def _application_certificates_are_pushed(self) -> bool:
        """Returns whether application certificate are stored.

        Returns:
            bool: Whether application certificate are stored.
        """
        if not self._container.exists(f"{self.BASE_CERTIFICATES_PATH}/admin_operator.pem"):
            logger.info("Admin Operator certificate is not pushed")
            return False
        if not self._container.exists(f"{self.BASE_CERTIFICATES_PATH}/admin_operator.pfx"):
            logger.info("Admin operator PFX package is not pushed")
            return False
        if not self._container.exists(f"{self.BASE_CERTIFICATES_PATH}/certifier.pem"):
            logger.info("Application certificate is not pushed")
            return False
        return True

    @property
    def _application_private_keys_are_pushed(self) -> bool:
        """Returns whether application private keys are pushed.

        Returns:
            bool: Whether application private keys are pushed.
        """
        if not self._container.exists(f"{self.BASE_CERTIFICATES_PATH}/certifier.key"):
            logger.info("Application private key is not pushed")
            return False
        if not self._container.exists(f"{self.BASE_CERTIFICATES_PATH}/admin_operator.key.pem"):
            logger.info("Admin operator private key is not pushed")
            return False
        return True

    @property
    def _db_relation_created(self) -> bool:
        """Checks whether db relation is created.

        Returns:
            bool: Whether required relation
        """
        return self._relation_created("db")

    @property
    def _db_relation_established(self) -> bool:
        """Validates that database relation is established.

        Checks that there is a relation and that credentials have been passed.

        Returns:
            bool: Whether the database relation is established.
        """
        db_connection_string = self._get_db_connection_string
        if not db_connection_string:
            return False
        try:
            psycopg2.connect(
                f"dbname='{self.DB_NAME}' "
                f"user='{db_connection_string.user}' "
                f"host='{db_connection_string.host}' "
                f"password='{db_connection_string.password}'"
            ).close()
            return True
        except psycopg2.OperationalError:
            return False

    @property
    def _pebble_layer(self) -> Layer:
        """Returns Pebble layer object containing the workload startup service.

        Returns:
            Layer: Pebble layer
        """
        return Layer(
            {
                "summary": f"{self._service_name} pebble layer",
                "services": {
                    self._service_name: {
                        "override": "replace",
                        "startup": "enabled",
                        "command": "/usr/bin/envdir "
                        "/var/opt/magma/envdir "
                        "/var/opt/magma/bin/certifier "
                        f"-cac={self.BASE_CERTIFICATES_PATH}/certifier.pem "
                        f"-cak={self.BASE_CERTIFICATES_PATH}/certifier.key "
                        f"-vpnc={self.BASE_CERTIFICATES_PATH}/vpn_ca.crt "
                        f"-vpnk={self.BASE_CERTIFICATES_PATH}/vpn_ca.key "
                        "-logtostderr=true "
                        "-v=0",
                        "environment": {
                            "DATABASE_SOURCE": f"dbname={self.DB_NAME} "  # type: ignore[union-attr]  # noqa: E501
                            f"user={self._get_db_connection_string.user} "
                            f"password={self._get_db_connection_string.password} "
                            f"host={self._get_db_connection_string.host} "
                            f"sslmode=disable",
                            "SQL_DRIVER": "postgres",
                            "SQL_DIALECT": "psql",
                            "SERVICE_HOSTNAME": "magma-orc8r-certifier",
                            "SERVICE_REGISTRY_MODE": "k8s",
                            "SERVICE_REGISTRY_NAMESPACE": self._namespace,
                        },
                    }
                },
            }
        )

    @property
    def _certificates_relation_created(self) -> bool:
        """Returns whether the certificates relation is created.

        Returns:
            bool: Whether the certificates relation is created.
        """
        return self._relation_created("certificates")

    @property
    def _replicas_relation_created(self) -> bool:
        """Returns whether the replicas  relation is created.

        Returns:
            bool: Whether the certificates relation is created.
        """
        return self._relation_created("replicas")

    @property
    def _get_db_connection_string(self) -> Optional[ConnectionString]:
        """Returns DB connection string provided by the DB relation.

        Returns:
            ConnectionString: Database connection object.
        """
        try:
            db_relation = self.model.get_relation("db")
            return ConnectionString(db_relation.data[db_relation.app]["master"])  # type: ignore[union-attr, index]  # noqa: E501
        except (AttributeError, KeyError):
            return None

    @property
    def _domain_config(self) -> Optional[str]:
        """Returns domain config."""
        return self.model.config.get("domain")

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
    def _service_is_running(self) -> bool:
        """Returns whether workload service is running.

        Returns:
            bool: Whether workload service is running.
        """
        if self._container.can_connect():
            try:
                self._container.get_service(self._service_name)
                return True
            except ModelError:
                pass
        return False

    @property
    def _namespace(self) -> str:
        """Kubernetes namespace.

        Returns:
            str: Namespace
        """
        return self.model.name

    def _on_install(self, event: InstallEvent) -> None:
        """Juju event triggered only once when charm is installed.

        Args:
            event: Juju event

        Returns:
            None
        """
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return
        if not self._replicas_relation_created:
            self.unit.status = WaitingStatus("Waiting for replicas relation to be created")
            event.defer()
            return
        if self.unit.is_leader():
            self._generate_root_private_key()
            self._generate_application_private_keys()
        else:
            if not self._application_private_keys_are_stored:
                self.unit.status = WaitingStatus(
                    "Waiting for leader to generate application private keys"
                )
                event.defer()
                return
            if not self._root_private_key_is_stored:
                self.unit.status = WaitingStatus("Waiting for leader to generate root private key")
                event.defer()
                return
            if not self._application_certificates_are_stored:
                self.unit.status = WaitingStatus(
                    "Waiting for leader to generate application certificates"
                )
                event.defer()
                return
            if not self._root_certificates_are_stored:
                self.unit.status = WaitingStatus("Waiting for root certificates to be stored")
                event.defer()
                return
            self._push_root_certificates()
            self._push_application_certificates()
        self._push_metricsd_config_file()
        self._push_application_private_keys()
        self._push_root_private_key()

    def _on_config_changed(self, event: ConfigChangedEvent):
        """Triggered on config changes.

        Args:
            event (ConfigChangedEvent): Juju event

        Returns:
            None
        """
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return
        if self.unit.is_leader():
            self._on_leader_config_changed(event)
        else:
            self._on_non_leader_config_changed(event)

    def _on_leader_config_changed(self, event: ConfigChangedEvent) -> None:
        """Triggered on config changed for leader unit.

        If the 'domain' config changed, new root certificates will be requested and new
        application certificates will be generated.

        Args:
            event: Juju event

        Returns:
            None
        """
        if not self._domain_config_is_valid:
            self.unit.status = BlockedStatus("Config 'domain' is not valid")
            event.defer()
            return
        if not self._root_private_key_is_stored:
            self.unit.status = WaitingStatus("Waiting for root private key to be generated")
            event.defer()
            return
        if not self._application_private_keys_are_stored:
            self.unit.status = WaitingStatus("Waiting for application private key to be generated")
            event.defer()
            return
        if not self._root_csr_is_stored:
            self._generate_root_csr()
            if self._certificates_relation_created:
                self._request_certificate_based_on_stored_csr()
                self.unit.status = WaitingStatus(
                    "Waiting to receive new certificate from provider"
                )
            else:
                self.unit.status = BlockedStatus(
                    "Waiting for tls-certificates relation to be created"
                )
        if not self._stored_root_csr_matches_config:
            old_csr = self._root_csr
            self._generate_root_csr()
            if self._certificates_relation_created:
                self.tls_certificates_requirer.request_certificate_renewal(
                    old_certificate_signing_request=old_csr.encode(),  # type: ignore[union-attr]  # noqa: E501
                    new_certificate_signing_request=self._root_csr.encode(),  # type: ignore[union-attr]  # noqa: E501
                )
                self.unit.status = WaitingStatus(
                    "Waiting to receive new certificate from provider"
                )
            else:
                self.unit.status = BlockedStatus(
                    "Waiting for tls-certificates relation to be created"
                )
        if (
            not self._application_certificates_are_stored
            or not self._stored_application_certificate_matches_config  # noqa: W503
        ):
            self._generate_application_certificates()
            self._push_application_certificates()

    def _on_non_leader_config_changed(self, event: ConfigChangedEvent):
        """Triggered on config changed for non-leader unit.

        Pushes application certificates to workload.

        Args:
            event: Juju event

        Returns:
            None
        """
        if not self._root_csr_is_stored or not self._stored_root_csr_matches_config:
            self.unit.status = WaitingStatus("Waiting for leader to generate a root csr")
            event.defer()
            return
        if not self._application_certificates_are_stored:
            self.unit.status = WaitingStatus(
                "Waiting for leader to generate application certificates"
            )
            event.defer()
            return
        if not self._stored_application_certificate_matches_config:
            self.unit.status = WaitingStatus(
                "Waiting for leader to generate new application certificates"
            )
            event.defer()
            return
        self._push_application_certificates()

    def _on_magma_orc8r_certifier_pebble_ready(
        self, event: Union[PebbleReadyEvent, CertificateAvailableEvent]
    ) -> None:
        """Juju event triggered when pebble is ready.

        Args:
            event: Juju event

        Returns:
            None
        """
        if not self._domain_config_is_valid:
            self.unit.status = BlockedStatus("Config 'domain' is not valid")
            event.defer()
            return
        if not self._db_relation_created:
            self.unit.status = BlockedStatus("Waiting for database relation to be created")
            event.defer()
            return
        if not self._certificates_relation_created:
            self.unit.status = BlockedStatus("Waiting for tls-certificates relation to be created")
            event.defer()
            return
        if not self._db_relation_established:
            self.unit.status = WaitingStatus("Waiting for db relation to be ready")
            event.defer()
            return
        if not self._root_private_key_is_pushed:
            self.unit.status = WaitingStatus("Waiting for root private key to be pushed")
            event.defer()
            return
        if not self._application_private_keys_are_pushed:
            self.unit.status = WaitingStatus("Waiting for application private keys to be pushed")
            event.defer()
            return
        if not self._application_certificates_are_pushed:
            self.unit.status = WaitingStatus("Waiting for application certificates to be pushed")
            event.defer()
            return
        if not self._root_certificates_are_pushed:
            self.unit.status = WaitingStatus("Waiting for root certificates to be pushed")
            event.defer()
            return
        self._configure_magma_orc8r_certifier(event)

    def _generate_root_csr(self) -> None:
        """Generates a CSR with the domain name in the Juju config.

        Returns:
            None
        """
        peer_relation = self.model.get_relation("replicas")
        if not self._domain_config_is_valid:
            raise ValueError("Domain config is not valid")
        if not peer_relation:
            raise RuntimeError("No peer relation")
        csr = generate_csr(
            private_key=self._root_private_key.encode(), subject=f"*.{self._domain_config}"  # type: ignore[union-attr]  # noqa: E501
        )
        self._store_root_csr(csr.decode())
        logger.info("Generated CSR for root certificate")

    def _on_certificates_relation_created(self, event: RelationJoinedEvent) -> None:
        """Juju event triggered when the certificates relation is created.

        Args:
            event: Juju event

        Returns:
            None
        """
        if not self.unit.is_leader():
            return
        if not self._replicas_relation_created:
            self.unit.status = WaitingStatus("Waiting for peer relation to be created")
            event.defer()
            return
        if not self._root_csr:
            self.unit.status = WaitingStatus("Waiting for root CSR to be generated")
            event.defer()
            return
        self._request_certificate_based_on_stored_csr()

    def _request_certificate_based_on_stored_csr(self):
        csr = self._root_csr
        if not csr:
            raise RuntimeError("No stored root CSR.")
        self.tls_certificates_requirer.request_certificate_creation(
            certificate_signing_request=csr.encode()
        )

    def _on_certificate_available(self, event: CertificateAvailableEvent) -> None:
        """Runs whenever the certificates available event is triggered.

        Pushes the certificates retrieved from the relation data to the workload container.

        Args:
            event (CertificateAvailableEvent): Custom Juju event for certificate available.

        Returns:
            None
        """
        if event.certificate_signing_request != self._root_csr:
            logger.info("Certificate's CSR doesn't match stored root CSR")
            return
        peer_relation = self.model.get_relation("replicas")
        if not peer_relation:
            logger.info("No peer relation created")
            event.defer()
            return
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return
        if self.unit.is_leader():
            self._store_root_ca_certificate(event.ca)
            self._store_root_certificate(event.certificate)
        else:
            if (
                not self._root_certificates_are_stored
                or not self._stored_root_certificate_matches_certificate(  # noqa: W503
                    event.certificate
                )
            ):
                self.unit.status = WaitingStatus("Waiting for leader to store root certificates")
                event.defer()
                return
        self._push_root_certificates()
        self._on_magma_orc8r_certifier_pebble_ready(event)

    def _on_database_relation_joined(self, event: RelationJoinedEvent) -> None:
        """Event handler for database relation change.

        - Sets the event.database field on the database joined event.
        - Required because setting the database name is only possible
          from inside the event handler per https://github.com/canonical/ops-lib-pgsql/issues/2
        - Sets our database parameters based on what was provided
          in the relation event.

        Args:
            event (RelationJoinedEvent): Juju relation joined event

        Returns:
            None
        """
        if self.unit.is_leader():
            event.database = self.DB_NAME  # type: ignore[attr-defined]

    def _push_metricsd_config_file(self) -> None:
        """Writes the config file for metricsd in the workload container.

        Returns:
            None
        """
        metricsd_config = (
            f'prometheusQueryAddress: "{self.PROMETHEUS_URL}"\n'
            f'alertmanagerApiURL: "{self.ALERTMANAGER_URL}/api/v2"\n'
            '"profile": "prometheus"\n'
        )
        self._container.push(path=f"{self.BASE_CONFIG_PATH}/metricsd.yml", source=metricsd_config)

    def _configure_magma_orc8r_certifier(
        self, event: Union[PebbleReadyEvent, CertificateAvailableEvent]
    ) -> None:
        """Adds layer to pebble config if the proposed config is different from the current one.

        Args:
            event (PebbleReadyEvent): Juju Pebble ready event

        Returns:
            None
        """
        if self._container.can_connect():
            plan = self._container.get_plan()
            layer = self._pebble_layer
            if plan.services != layer.services:
                self.unit.status = MaintenanceStatus("Configuring pod")
                self._container.add_layer(self._container_name, layer, combine=True)
                self._container.restart(self._service_name)
                logger.info(f"Restarted container {self._service_name}")
                self._update_relations()
                self.unit.status = ActiveStatus()
        else:
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()

    def _update_relations(self) -> None:
        """Updates all the "provided" relation with the workload service status.

        Returns:
            None
        """
        if not self.unit.is_leader():
            return
        relations = self.model.relations[self.provided_relation_name]
        for relation in relations:
            self._update_relation_active_status(
                relation=relation, is_active=self._service_is_running
            )

    def _generate_application_certificates(self) -> None:
        """Generates application certificates.

        The following certificates are created:
            - certifier.pem
            - admin_operator.pem
            - admin_operator.pfx
            - admin_operator_password

        Returns:
            None
        """
        if not self._application_private_key:
            raise RuntimeError("Application private key not available")
        if not self._admin_operator_private_key:
            raise RuntimeError("Admin Operator private key not available")
        application_ca_certificate = generate_ca(
            private_key=self._application_private_key.encode(),
            subject=f"certifier.{self._domain_config}",
        )
        admin_operator_csr = generate_csr(
            private_key=self._admin_operator_private_key.encode(),
            subject="admin_operator",
        )
        admin_operator_certificate = generate_certificate(
            csr=admin_operator_csr,
            ca=application_ca_certificate,
            ca_key=self._application_private_key.encode(),
        )
        password = self._generate_password()
        admin_operator_pfx = generate_pfx_package(
            private_key=self._admin_operator_private_key.encode(),
            certificate=admin_operator_certificate,
            package_password=password,
        )
        self._store_application_ca_certificate(application_ca_certificate.decode())
        self._store_admin_operator_certificate(admin_operator_certificate.decode())
        self._store_admin_operator_pfx(base64.b64encode(admin_operator_pfx).decode())
        self._store_admin_operator_pfx_password(password)
        logger.info("Generated Application Certificates")

    def _generate_application_private_keys(self) -> None:
        """Generates application private keys.

        Returns:
            None
        """
        application_private_key = generate_private_key()
        admin_operator_private_key = generate_private_key()
        self._store_application_private_key(application_private_key.decode())
        self._store_admin_operator_private_key(admin_operator_private_key.decode())
        logger.info("Generated application private keys")

    def _generate_root_private_key(self) -> None:
        """Generates the root private key and stores it in peer relation data.

        Returns:
            None
        """
        root_private_key = generate_private_key()
        self._store_root_private_key(root_private_key.decode())
        logger.info("Generated root private key")

    def _push_application_certificates(self) -> None:
        """Pushes application certificates to the workload container.

        The following certificates are pushed:
            - certifier.pem
            - admin_operator.pem
            - admin_operator.pfx

        Returns:
            None
        """
        if not self._application_certificate:
            raise RuntimeError("Application certificate is not available")
        if not self._admin_operator_certificate:
            raise RuntimeError("Admin Operator certificate is not available")
        if not self._admin_operator_pfx:
            raise RuntimeError("Admin Operator PFX package is not available")
        self._container.push(
            path=f"{self.BASE_CERTIFICATES_PATH}/certifier.pem",
            source=self._application_certificate,
        )
        self._container.push(
            path=f"{self.BASE_CERTIFICATES_PATH}/admin_operator.pem",
            source=self._admin_operator_certificate,
        )
        self._container.push(
            path=f"{self.BASE_CERTIFICATES_PATH}/admin_operator.pfx",
            source=base64.b64decode(self._admin_operator_pfx),
        )
        logger.info("Pushed application certificates")

    def _push_application_private_keys(self) -> None:
        """Pushes application private keys to the workload container.

        The following keys are pushed:
            - certifier.key
            - admin_operator.key.pem
            - admin_operator.pfx

        Returns:
            None
        """
        if not self._application_private_key:
            raise RuntimeError("Application private key is not available")
        if not self._admin_operator_private_key:
            raise RuntimeError("Admin Operator private key is not available")
        self._container.push(
            path=f"{self.BASE_CERTIFICATES_PATH}/certifier.key",
            source=self._application_private_key,
        )
        self._container.push(
            path=f"{self.BASE_CERTIFICATES_PATH}/admin_operator.key.pem",
            source=self._admin_operator_private_key,
        )
        logger.info("Pushed application private keys")

    def _push_root_certificates(self) -> None:
        """Pushes root certificates to workload container.

        Returns:
            None
        """
        if not self._root_ca_certificate:
            raise RuntimeError("Root CA certificate is not available")
        if not self._root_certificate:
            raise RuntimeError("Root certificate is not available")
        self._container.push(
            path=f"{self.BASE_CERTIFICATES_PATH}/rootCA.pem", source=self._root_ca_certificate
        )
        self._container.push(
            path=f"{self.BASE_CERTIFICATES_PATH}/controller.crt", source=self._root_certificate
        )
        logger.info("Pushed root certificates")

    def _push_root_private_key(self) -> None:
        """Pushes root private key to workload container.

        Returns:
            None
        """
        if not self._root_private_key:
            raise RuntimeError("Root Private key not available.")
        self._container.push(
            path=f"{self.BASE_CERTIFICATES_PATH}/controller.key", source=self._root_private_key
        )
        logger.info("Pushed root private key")

    @property
    def _application_certificates_are_stored(self) -> bool:
        """Returns whether certificates are stored in relation data.

        Returns:
            bool: Whether certificates have been generated.
        """
        if not self._application_certificate:
            logger.info("Application certificate is not stored")
            return False
        if not self._admin_operator_certificate:
            logger.info("Admin Operator certificate is not stored")
            return False
        if not self._admin_operator_pfx_password:
            logger.info("Admin Operator PFX password is not stored")
            return False
        if not self._admin_operator_pfx:
            logger.info("Admin Operator PFX package is not stored")
            return False
        return True

    @property
    def _stored_application_certificate_matches_config(self) -> bool:
        """Returns whether application certificates matches config.

        Returns:
            bool: Whether certificates have been generated.
        """
        if not self._application_certificate:
            raise RuntimeError("Application certificates not stored")
        application_certificate = x509.load_pem_x509_certificate(
            data=self._application_certificate.encode()
        )
        for subject in application_certificate.subject:
            if subject.value == f"certifier.{self._domain_config}":
                return True
        logger.info("Stored application certificates does not match config")
        return False

    @property
    def _application_private_keys_are_stored(self) -> bool:
        """Returns whether certificates are stored in relation data.

        Returns:
            bool: Whether certificates have been generated.
        """
        if not self._application_private_key:
            logger.info("Application private key not stored")
            return False
        if not self._admin_operator_private_key:
            logger.info("Admin operator private key not stored")
            return False
        return True

    @property
    def _application_private_key(self) -> Optional[str]:
        """Returns application private key.

        Returns:
            str: Private key
        """
        return self._get_item_from_relation_data("application_private_key")

    @property
    def _application_certificate(self) -> Optional[str]:
        """Returns application certificate.

        Returns:
            str: Certificate
        """
        return self._get_item_from_relation_data("application_certificate")

    @property
    def _admin_operator_private_key(self) -> Optional[str]:
        """Returns admin operator private key.

        Returns:
            str: Private key
        """
        return self._get_item_from_relation_data("admin_operator_private_key")

    @property
    def _admin_operator_certificate(self) -> Optional[str]:
        """Returns admin operator certificate.

        Returns:
            str: Certificate
        """
        return self._get_item_from_relation_data("admin_operator_certificate")

    @property
    def _admin_operator_pfx_password(self) -> Optional[str]:
        """Returns admin operator password.

        Returns:
            str: Password
        """
        return self._get_item_from_relation_data("admin_operator_pfx_password")

    @property
    def _admin_operator_pfx(self) -> Optional[str]:
        """Returns admin operator pfx package.

        Returns:
            str: PFX Package
        """
        return self._get_item_from_relation_data("admin_operator_pfx")

    @property
    def _root_private_key(self) -> Optional[str]:
        """Returns root private key.

        Returns:
            str: Private key
        """
        return self._get_item_from_relation_data("root_private_key")

    @property
    def _root_csr(self) -> Optional[str]:
        """Returns root CSR.

        Returns:
            str: Root CSR
        """
        return self._get_item_from_relation_data("root_csr")

    @property
    def _root_certificate(self) -> Optional[str]:
        """Returns root certificate.

        Returns:
            str: Root certificate
        """
        return self._get_item_from_relation_data("root_certificate")

    @property
    def _root_ca_certificate(self) -> Optional[str]:
        """Returns root ca certificate.

        Returns:
            str: Root CA certificate
        """
        return self._get_item_from_relation_data("root_ca_certificate")

    @property
    def _root_private_key_is_stored(self) -> bool:
        """Returns whether private key is stored in peer relation data.

        Returns:
            bool: True/False
        """
        if self._root_private_key:
            return True
        else:
            return False

    @property
    def _root_csr_is_stored(self) -> bool:
        """Returns whether root CSR is stored in peer relation data.

        Returns:
            bool: True/False
        """
        if not self._root_csr:
            logger.info("Root CSR not stored")
            return False
        return True

    @property
    def _stored_root_csr_matches_config(self) -> bool:
        """Returns whether the stored root CSR matches the config.

        Returns:
            bool: True/False
        """
        if not self._root_csr:
            raise RuntimeError("No stored root CSR")
        csr_object = x509.load_pem_x509_csr(data=self._root_csr.encode())
        if f"*.{self._domain_config}" == list(csr_object.subject)[0].value:
            return True
        else:
            logger.info("Root CSR subject doesn't match with config")
            return False

    @property
    def _root_certificates_are_stored(self) -> bool:
        """Returns whether root certificates are stored.

        Returns:
            bool: Whether root certificates are stored.
        """
        if not self._root_certificate:
            logger.info("Root certificate not stored")
            return False
        if not self._root_ca_certificate:
            logger.info("Root CA certificate not stored")
            return False
        return True

    def _stored_root_certificate_matches_certificate(self, certificate: str) -> bool:
        """Returns whether root certificate matches provided certificate.

        Args:
            certificate: TLS Certificate.

        Returns:
            bool: Whether root certificate matches provided certificate.
        """
        if not self._root_certificate:
            raise RuntimeError("Root certificate not stored")
        return certificate == self._root_certificate

    def _store_application_private_key(self, private_key: str) -> None:
        self._store_item_in_peer_relation_data(key="application_private_key", value=private_key)

    def _store_application_ca_certificate(self, certificate: str) -> None:
        self._store_item_in_peer_relation_data(key="application_certificate", value=certificate)

    def _store_admin_operator_private_key(self, private_key: str) -> None:
        self._store_item_in_peer_relation_data(key="admin_operator_private_key", value=private_key)

    def _store_admin_operator_certificate(self, certificate: str) -> None:
        self._store_item_in_peer_relation_data(key="admin_operator_certificate", value=certificate)

    def _store_admin_operator_pfx(self, pfx: str) -> None:
        self._store_item_in_peer_relation_data(key="admin_operator_pfx", value=pfx)

    def _store_admin_operator_pfx_password(self, password: str) -> None:
        self._store_item_in_peer_relation_data(key="admin_operator_pfx_password", value=password)

    def _store_root_private_key(self, private_key: str) -> None:
        self._store_item_in_peer_relation_data(key="root_private_key", value=private_key)

    def _store_root_csr(self, csr: str) -> None:
        self._store_item_in_peer_relation_data(key="root_csr", value=csr)

    def _store_root_ca_certificate(self, ca_certificate: str) -> None:
        self._store_item_in_peer_relation_data(key="root_ca_certificate", value=ca_certificate)

    def _store_root_certificate(self, certificate: str) -> None:
        self._store_item_in_peer_relation_data(key="root_certificate", value=certificate)

    def _get_item_from_relation_data(self, item: str) -> Optional[str]:
        replicas = self.model.get_relation("replicas")
        if not replicas:
            return None
        return replicas.data[self.app].get(item, None)

    def _store_item_in_peer_relation_data(self, key: str, value: str) -> None:
        peer_relation = self.model.get_relation("replicas")
        if not peer_relation:
            raise RuntimeError("No peer relation")
        peer_relation.data[self.app].update({key: value})

    def _update_relation_active_status(self, relation: Relation, is_active: bool) -> None:
        """Updates the relation data content.

        Args:
            relation (Relation): Juju relation object
            is_active (bool): Whether the service is active or not

        Returns:
            None
        """
        relation.data[self.unit].update(
            {
                "active": str(is_active),
            }
        )

    def _relation_created(self, relation_name: str) -> bool:
        """Returns whether a given Juju relation was crated.

        Args:
            relation_name (str): Relation name

        Returns:
            str: Whether the relation was created.
        """
        if not self.model.get_relation(relation_name):
            return False
        return True

    @staticmethod
    def _encode_in_base64(byte_string: bytes) -> str:
        """Encodes given byte string in Base64.

        Args:
            byte_string (bytes): Byte data

        Returns:
            str: String of the bytes data.
        """
        return base64.b64encode(byte_string).decode("utf-8")

    @staticmethod
    def _generate_password() -> str:
        """Generates a random 12 character password.

        Returns:
            str: Password
        """
        chars = string.ascii_letters + string.digits
        return "".join(secrets.choice(chars) for _ in range(12))

    def _on_get_pfx_package_password(self, event: ActionEvent) -> None:
        """Sets the action result as the admin operator PFX package password.

        Args:
            event (ActionEvent): Juju event

        Returns:
            None
        """
        if not self._admin_operator_pfx:
            event.fail("Admin Operator PFX package is not available")
            return
        event.set_results(
            {
                "password": self._admin_operator_pfx_password,
            }
        )

    def _on_get_root_csr_action(self, event: ActionEvent) -> None:
        """Sets the action result as the root CSR.

        Args:
            event (ActionEvent): Juju event

        Returns:
            None
        """
        if not self._root_csr:
            event.fail("Admin Operator PFX package is not available")
            return
        event.set_results(
            {
                "csr": self._root_csr,
            }
        )

    def _on_admin_operator_certificate_request(
        self, event: AdminOperatorCertificateRequestEvent
    ) -> None:
        """Triggered when a certificate request is made on the admin_operator relation.

        Args:
            event (AdminOperatorCertificateRequestEvent): Juju event.

        Returns:
            None
        """
        if not self._container.can_connect():
            logger.info("Container not yet available")
            event.defer()
            return
        try:
            certificate = self._container.pull(
                path=f"{self.BASE_CERTIFICATES_PATH}/admin_operator.pem"
            )
            private_key = self._container.pull(
                path=f"{self.BASE_CERTIFICATES_PATH}/admin_operator.key.pem"
            )
        except ops.pebble.PathError:
            logger.info("Certificate 'admin-operator' not yet available")
            event.defer()
            return
        certificate_string = certificate.read()
        private_key_string = private_key.read()
        self.certificates_admin_operator_provider.set_certificate(
            relation_id=event.relation_id,
            certificate=str(certificate_string),
            private_key=str(private_key_string),
        )

    def _on_certifier_certificate_request(self, event: CertifierCertificateRequestEvent) -> None:
        """Triggered when a certificate request is made on the cert-certifier relation.

        Args:
            event (CertifierCertificateRequestEvent): Juju event

        Returns:
            None
        """
        if not self._container.can_connect():
            logger.info("Container not yet available")
            event.defer()
            return
        try:
            certificate = self._container.pull(path=f"{self.BASE_CERTIFICATES_PATH}/certifier.pem")
        except ops.pebble.PathError:
            logger.info("Certificate 'certifier' not yet available")
            event.defer()
            return
        certificate_string = certificate.read()
        self.certificates_certifier_provider.set_certificate(
            relation_id=event.relation_id,
            certificate=str(certificate_string),
        )

    def _on_controller_certificate_request(self, event: ControllerCertificateRequestEvent) -> None:
        """Triggered when a certificate request is made on the cert-controller relation.

        Args:
            event (ControllerCertificateRequestEvent): Juju event

        Returns:
            None
        """
        if not self._container.can_connect():
            logger.info("Container not yet available")
            event.defer()
            return
        try:
            certificate = self._container.pull(
                path=f"{self.BASE_CERTIFICATES_PATH}/controller.crt"
            )
            private_key = self._container.pull(
                path=f"{self.BASE_CERTIFICATES_PATH}/controller.key"
            )
        except ops.pebble.PathError:
            logger.info("Certificate 'controller' not yet available")
            event.defer()
            return
        certificate_string = certificate.read()
        private_key_string = private_key.read()
        self.certificates_controller_provider.set_certificate(
            relation_id=event.relation_id,
            certificate=str(certificate_string),
            private_key=str(private_key_string),
        )

    def _on_certificate_expiring(
        self,
        event: Union[CertificateExpiringEvent, CertificateExpiredEvent, CertificateRevokedEvent],
    ) -> None:
        """Triggered on certificate expiring/expired/revoked events.

        Will ask for new certificates.

        Args:
            event: Juju event

        Returns:
            None
        """
        if not self.unit.is_leader():
            return
        if not self._domain_config_is_valid:
            self.unit.status = BlockedStatus("Config 'domain' is not valid")
            return
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return
        if not self._root_private_key_is_stored:
            self.unit.status = WaitingStatus("Waiting for root private key to be generated")
            event.defer()
            return
        if not self._root_csr_is_stored:
            self._generate_root_csr()
            self._request_certificate_based_on_stored_csr()
            self.unit.status = WaitingStatus("Waiting to receive new certificate from provider")
            return
        old_csr = self._root_csr
        self._generate_root_csr()
        self.tls_certificates_requirer.request_certificate_renewal(
            old_certificate_signing_request=old_csr.encode(),  # type: ignore[union-attr]
            new_certificate_signing_request=self._root_csr.encode(),  # type: ignore[union-attr]
        )
        self.unit.status = WaitingStatus("Waiting to receive new certificate from provider")


if __name__ == "__main__":
    main(MagmaOrc8rCertifierCharm)
