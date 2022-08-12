#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Maintains and verifies signed client certificates and their associated identities."""

import base64
import logging
import secrets
import string
from typing import Optional, Union

import ops.lib
import psycopg2  # type: ignore[import]
from charms.magma_orc8r_certifier.v0.cert_admin_operator import (  # type: ignore[import]
    CertAdminOperatorProvides,
)
from charms.magma_orc8r_certifier.v0.cert_admin_operator import (
    CertificateRequestEvent as AdminOperatorCertificateRequestEvent,
)
from charms.magma_orc8r_certifier.v0.cert_bootstrapper import (  # type: ignore[import]  # noqa: E501
    CertBootstrapperProvides,
)
from charms.magma_orc8r_certifier.v0.cert_bootstrapper import (
    CertificateRequestEvent as BootstrapperCertificateRequestEvent,
)
from charms.magma_orc8r_certifier.v0.cert_certifier import (  # type: ignore[import]  # noqa: E501
    CertCertifierProvides,
)
from charms.magma_orc8r_certifier.v0.cert_certifier import (
    CertificateRequestEvent as CertifierCertificateRequestEvent,
)
from charms.magma_orc8r_certifier.v0.cert_controller import (  # type: ignore[import]  # noqa: E501
    CertControllerProvides,
)
from charms.magma_orc8r_certifier.v0.cert_controller import (
    CertificateRequestEvent as ControllerCertificateRequestEvent,
)
from charms.observability_libs.v1.kubernetes_service_patch import (  # type: ignore[import]
    KubernetesServicePatch,
    ServicePort,
)
from charms.tls_certificates_interface.v1.tls_certificates import (  # type: ignore[import]
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
    RelationCreatedEvent,
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
    BASE_CERTS_PATH = "/var/opt/magma/certs"

    # TODO: The various URL's should be provided through relationships
    PROMETHEUS_URL = "http://orc8r-prometheus:9090"
    ALERTMANAGER_URL = "http://orc8r-alertmanager:9093"

    def __init__(self, *args):
        """Initializes all events that need to be observed."""
        super().__init__(*args)
        self.certificates = TLSCertificatesRequiresV1(self, "certificates")
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.cert_admin_operator = CertAdminOperatorProvides(self, "cert-admin-operator")
        self.cert_certifier = CertCertifierProvides(self, "cert-certifier")
        self.cert_controller = CertControllerProvides(self, "cert-controller")
        self.cert_bootstrapper = CertBootstrapperProvides(self, "cert-bootstrapper")
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
        self.framework.observe(
            self.certificates.on.certificate_available, self._on_certificate_available
        )
        self.framework.observe(
            self.certificates.on.certificate_expiring, self._on_certificate_expiring
        )
        self.framework.observe(
            self.on.certificates_relation_joined, self._on_certificates_relation_joined
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
            self.cert_admin_operator.on.certificate_request,
            self._on_admin_operator_certificate_request,
        )
        self.framework.observe(
            self.cert_certifier.on.certificate_request,
            self._on_certifier_certificate_request,
        )
        self.framework.observe(
            self.cert_controller.on.certificate_request,
            self._on_controller_certificate_request,
        )
        self.framework.observe(
            self.cert_bootstrapper.on.private_key_request,
            self._on_bootstrapper_private_key_request,
        )
        self.framework.observe(
            self.on.replicas_relation_created, self._on_replicas_relation_created
        )

    @property
    def _root_certs_are_pushed(self) -> bool:
        """Returns whether root certificate are stored.

        Returns:
            bool: Whether root certificate are stored.
        """
        return (
            self._container.exists(f"{self.BASE_CERTS_PATH}/controller.crt")
            and self._container.exists(f"{self.BASE_CERTS_PATH}/controller.key")  # noqa: W503
            and self._container.exists(f"{self.BASE_CERTS_PATH}/rootCA.pem")  # noqa: W503
        )

    @property
    def _application_certificates_are_pushed(self) -> bool:
        """Returns whether application certificate are stored.

        Returns:
            bool: Whether application certificate are stored.
        """
        return (
            self._container.exists(f"{self.BASE_CERTS_PATH}/admin_operator.pem")
            and self._container.exists(f"{self.BASE_CERTS_PATH}/admin_operator.pfx")  # noqa: W503
            and self._container.exists(f"{self.BASE_CERTS_PATH}/certifier.pem")  # noqa: W503
        )

    @property
    def _application_private_keys_are_pushed(self) -> bool:
        """Returns whether application private keys are pushed.

        Returns:
            bool: Whether application private keys are pushed.
        """
        return (
            self._container.exists(f"{self.BASE_CERTS_PATH}/admin_operator.key.pem")
            and self._container.exists(f"{self.BASE_CERTS_PATH}/certifier.key")  # noqa: W503
            and self._container.exists(f"{self.BASE_CERTS_PATH}/bootstrapper.key")  # noqa: W503
        )

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
                        f"-cac={self.BASE_CERTS_PATH}/certifier.pem "
                        f"-cak={self.BASE_CERTS_PATH}/certifier.key "
                        f"-vpnc={self.BASE_CERTS_PATH}/vpn_ca.crt "
                        f"-vpnk={self.BASE_CERTS_PATH}/vpn_ca.key "
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
        return self.model.config.get("domain")

    @property
    def _domain_config_is_valid(self) -> bool:
        """Returns whether the "domain" config is valid.

        For now simply checks if the config is set as a non-null value.

        Returns:
            bool: Whether the domain is a valid one.
        """
        if not self._domain_config:
            return False
        return True

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
        self._push_metricsd_config_file()

    def _on_config_changed(self, event: ConfigChangedEvent):
        if self.unit.is_leader():
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
            if not self._application_private_keys_are_stored:
                self.unit.status = WaitingStatus(
                    "Waiting for application private key to be generated"
                )
                event.defer()
                return
            if not self._root_csr_is_stored:
                self._generate_root_csr()
            if not self._application_certificates_are_stored:
                self._generate_application_certificates()
                self._push_application_certificates()
        else:
            if not self._root_csr_is_stored:
                self.unit.status = WaitingStatus("Waiting for leader to generate root csr")
                event.defer()
                return
            if not self._application_certificates_are_stored:
                self.unit.status = WaitingStatus(
                    "Waiting for leader to generate application certificates"
                )
                event.defer()
                return
        self._on_magma_orc8r_certifier_pebble_ready(event)

    def _on_replicas_relation_created(self, event: RelationCreatedEvent) -> None:
        """Juju event triggered when the replicas relation is created.

        Args:
            event: Juju event

        Returns:
            None
        """
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return
        if self.unit.is_leader():
            self._generate_root_private_key()
            self._generate_application_private_keys()
        else:
            if not self._application_private_keys_are_stored:
                self.unit.status = WaitingStatus(
                    "Waiting for application private keys to be stored"
                )
                event.defer()
                return
            if not self._root_private_key_is_stored:
                self.unit.status = WaitingStatus("Waiting for root private key to be stored")
                event.defer()
                return
        self._push_application_private_keys()
        self._push_root_private_key()

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
        if not self._root_certs_are_pushed:
            self.unit.status = WaitingStatus("Waiting for root certs to be available")
            event.defer()
            return
        if not self._application_private_keys_are_pushed:
            self.unit.status = WaitingStatus("Waiting for application certs to be available")
            event.defer()
            return
        if not self._application_certificates_are_pushed:
            self.unit.status = WaitingStatus("Waiting for application certs to be available")
            event.defer()
            return
        self._configure_magma_orc8r_certifier(event)

    def _generate_root_csr(self) -> None:
        """Generates a CSR with the domain name in the Juju config.

        Returns:
            None
        """
        domain_name = self._domain_config
        peer_relation = self.model.get_relation("replicas")
        if not domain_name:
            raise RuntimeError("No domain name set")
        if not peer_relation:
            raise RuntimeError("No peer relation")
        if not self._domain_config_is_valid:
            raise ValueError("Domain config is not valid")
        if not self._root_private_key:
            raise RuntimeError("No stored private key")
        csr = generate_csr(
            private_key=self._root_private_key.encode(), subject=f"*.{self._domain_config}"
        )

        self._store_root_csr(csr.decode())
        logger.info("Generated CSR for root certificate")

    def _on_certificates_relation_joined(self, event: RelationJoinedEvent) -> None:
        """Juju event triggered when pebble is ready.

        Args:
            event: Juju event

        Returns:
            None
        """
        if not self.unit.is_leader():
            return
        peer_relation = self.model.get_relation("replicas")
        if not peer_relation:
            logger.info("Waiting for peer relation to be created")
            event.defer()
            return
        csr = self._root_csr
        if not csr:
            logger.info("Waiting for root CSR to be generated")
            event.defer()
            return
        self.certificates.request_certificate_creation(certificate_signing_request=csr.encode())

    def _on_certificate_available(self, event: CertificateAvailableEvent) -> None:
        """Runs whenever the certificates available event is triggered.

        Pushes the certificates retrieved from the relation data to the workload container.

        Args:
            event (CertificateAvailableEvent): Custom Juju event for certificate available.

        Returns:
            None
        """
        if not self._container.can_connect():
            logger.info("Cant connect to container - Won't push certificates to workload")
            event.defer()
            return
        if event.certificate_signing_request != self._root_csr:
            logger.info("Certificate's CSR doesn't match stored root CSR")
            return
        peer_relation = self.model.get_relation("replicas")
        if not peer_relation:
            logger.info("No peer relation created")
            event.defer()
            return
        if self.unit.is_leader():
            self._store_root_ca_certificate(event.ca)
            self._store_root_certificate(event.certificate)
        else:
            if not self._root_certificate_is_stored(event.certificate):
                self.unit.status = WaitingStatus("Waiting for leader to store root certificates.")
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
        if not self._application_private_key or not self._admin_operator_private_key:  # noqa: W503
            raise RuntimeError("Application certificates are not available")
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
        bootstrapper_key = generate_private_key()
        self._store_application_private_key(application_private_key.decode())
        self._store_admin_operator_private_key(admin_operator_private_key.decode())
        self._store_bootstrapper_private_key(bootstrapper_key.decode())
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
        if (
            not self._application_certificate
            or not self._admin_operator_certificate  # noqa: W503
            or not self._admin_operator_pfx  # noqa: W503
        ):
            raise RuntimeError("Application certificates are not available")
        self._container.push(
            path=f"{self.BASE_CERTS_PATH}/certifier.pem",
            source=self._application_certificate,
        )
        self._container.push(
            path=f"{self.BASE_CERTS_PATH}/admin_operator.pem",
            source=self._admin_operator_certificate,
        )
        self._container.push(
            path=f"{self.BASE_CERTS_PATH}/admin_operator.pfx",
            source=base64.b64decode(self._admin_operator_pfx),
        )

    def _push_application_private_keys(self) -> None:
        """Pushes application certificates to the workload container.

        The following keys are pushed:
            - certifier.pem
            - certifier.key
            - admin_operator.pem
            - admin_operator.key.pem
            - admin_operator.pfx

        Returns:
            None
        """
        if (
            not self._application_private_key  # noqa: W503
            or not self._admin_operator_private_key  # noqa: W503
            or not self._bootstrapper_private_key  # noqa: W503
        ):
            raise RuntimeError("Application private keys are not available")
        self._container.push(
            path=f"{self.BASE_CERTS_PATH}/certifier.key",
            source=self._application_private_key,
        )
        self._container.push(
            path=f"{self.BASE_CERTS_PATH}/admin_operator.key.pem",
            source=self._admin_operator_private_key,
        )
        self._container.push(
            path=f"{self.BASE_CERTS_PATH}/bootstrapper.key", source=self._bootstrapper_private_key
        )

    def _push_root_certificates(self) -> None:
        """Pushes root certificates to workload container.

        Returns:
            None
        """
        if not self._root_ca_certificate or not self._root_certificate:
            raise RuntimeError("Root certificates not available.")
        self._container.push(
            path=f"{self.BASE_CERTS_PATH}/rootCA.pem", source=self._root_ca_certificate
        )
        self._container.push(
            path=f"{self.BASE_CERTS_PATH}/controller.crt", source=self._root_certificate
        )

    def _push_root_private_key(self) -> None:
        """Pushes root certificates to workload container.

        Returns:
            None
        """
        if not self._root_private_key:
            raise RuntimeError("Root Private key not available.")
        self._container.push(
            path=f"{self.BASE_CERTS_PATH}/controller.key", source=self._root_private_key
        )

    @property
    def _application_certificates_are_stored(self) -> bool:
        """Returns whether certificates are stored in relation data.

        Returns:
            bool: Whether certificates have been generated.
        """
        if (
            not self._application_certificate
            or not self._admin_operator_certificate  # noqa: W503
            or not self._admin_operator_pfx_password  # noqa: W503
            or not self._admin_operator_pfx  # noqa: W503
        ):
            logger.info("Application certificates not stored")
            return False
        application_certificate = x509.load_pem_x509_certificate(
            data=self._application_certificate.encode()
        )
        try:
            assert (
                f"certifier.{self._domain_config}"
                == list(application_certificate.subject)[0].value  # noqa: W503
            )
            return True
        except AssertionError:
            logger.info("Application CA Certificate domain name doesnt match with config value.")
            return False

    @property
    def _application_private_keys_are_stored(self) -> bool:
        """Returns whether certificates are stored in relation data.

        Returns:
            bool: Whether certificates have been generated.
        """
        if (
            self._application_private_key
            and self._admin_operator_private_key  # noqa: W503
            and self._bootstrapper_private_key  # noqa: W503
        ):
            return True
        else:
            logger.info("Application private keys not stored")
            return False

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
    def _bootstrapper_private_key(self) -> Optional[str]:
        """Returns bootstrapper private key.

        Returns:
            str: Private key
        """
        return self._get_item_from_relation_data("bootstrapper_private_key")

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
        csr_object = x509.load_pem_x509_csr(data=self._root_csr.encode())
        try:
            assert f"*.{self._domain_config}" == list(csr_object.subject)[0].value
            return True
        except AssertionError:
            logger.info("Root CSR subject doesn't match with config")
            return False

    def _root_certificate_is_stored(self, certificate: str):
        if not self._root_certificate:
            logger.info("Root certificate not stored")
            return False
        try:
            assert certificate == self._root_certificate
            return True
        except AssertionError:
            return False

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

    def _store_bootstrapper_private_key(self, private_key: str) -> None:
        self._store_item_in_peer_relation_data(key="bootstrapper_private_key", value=private_key)

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
        app_data = self.model.get_relation("replicas").data[self.app]  # type: ignore[union-attr]
        event.set_results(
            {
                "password": app_data.get("admin_operator_password"),
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
            certificate = self._container.pull(path=f"{self.BASE_CERTS_PATH}/admin_operator.pem")
            private_key = self._container.pull(
                path=f"{self.BASE_CERTS_PATH}/admin_operator.key.pem"
            )
        except ops.pebble.PathError:
            logger.info("Certificate 'admin-operator' not yet available")
            event.defer()
            return
        certificate_string = certificate.read()
        private_key_string = private_key.read()
        self.cert_admin_operator.set_certificate(
            relation_id=event.relation_id,
            certificate=certificate_string,
            private_key=private_key_string,
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
            certificate = self._container.pull(path=f"{self.BASE_CERTS_PATH}/certifier.pem")
        except ops.pebble.PathError:
            logger.info("Certificate 'certifier' not yet available")
            event.defer()
            return
        certificate_string = certificate.read()
        self.cert_certifier.set_certificate(
            relation_id=event.relation_id,
            certificate=certificate_string,
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
            certificate = self._container.pull(path=f"{self.BASE_CERTS_PATH}/controller.crt")
            private_key = self._container.pull(path=f"{self.BASE_CERTS_PATH}/controller.key")
        except ops.pebble.PathError:
            logger.info("Certificate 'controller' not yet available")
            event.defer()
            return
        certificate_string = certificate.read()
        private_key_string = private_key.read()
        self.cert_controller.set_certificate(
            relation_id=event.relation_id,
            certificate=certificate_string,
            private_key=private_key_string,
        )

    def _on_bootstrapper_private_key_request(
        self, event: BootstrapperCertificateRequestEvent
    ) -> None:
        """Triggered when a private key request is made on the cert-bootstrapper relation.

        Args:
            event (BootstrapperCertificateRequestEvent): Juju event

        Returns:
            None
        """
        if not self._container.can_connect():
            logger.info("Container not yet available")
            event.defer()
            return
        try:
            private_key = self._container.pull(path=f"{self.BASE_CERTS_PATH}/bootstrapper.key")
        except (ops.pebble.PathError, FileNotFoundError):
            logger.info("Certificate 'bootstrapper' not yet available")
            event.defer()
            return
        private_key_string = private_key.read()
        self.cert_bootstrapper.set_private_key(
            relation_id=event.relation_id,
            private_key=private_key_string,
        )

    def _on_certificate_expiring(
        self,
        event: Union[CertificateExpiringEvent, CertificateExpiredEvent, CertificateRevokedEvent],
    ) -> None:
        # TODO
        pass


if __name__ == "__main__":
    main(MagmaOrc8rCertifierCharm)
