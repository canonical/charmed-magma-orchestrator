#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""magma-orc8r-certifier.

magma-orc8r-certifier maintains and verifies signed client certificates and their associated
identities.
"""

import base64
import logging
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
from charms.magma_orc8r_certifier.v0.cert_bootstrapper import CertBootstrapperProvides
from charms.magma_orc8r_certifier.v0.cert_bootstrapper import (
    CertificateRequestEvent as BootstrapperCertificateRequestEvent,
)
from charms.magma_orc8r_certifier.v0.cert_certifier import CertCertifierProvides
from charms.magma_orc8r_certifier.v0.cert_certifier import (
    CertificateRequestEvent as CertifierCertificateRequestEvent,
)
from charms.magma_orc8r_certifier.v0.cert_controller import CertControllerProvides
from charms.magma_orc8r_certifier.v0.cert_controller import (
    CertificateRequestEvent as ControllerCertificateRequestEvent,
)
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from charms.tls_certificates_interface.v0.tls_certificates import (
    CertificateAvailableEvent,
    TLSCertificatesRequires,
)
from charms.observability_libs.v1.kubernetes_service_patch import (
    KubernetesServicePatch,
    ServicePort,
)
from ops.charm import (
    ActionEvent,
    CharmBase,
    InstallEvent,
    PebbleReadyEvent,
    RelationJoinedEvent,
)
from ops.framework import StoredState
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

from application_certificates import (
    generate_ca,
    generate_certificate,
    generate_csr,
    generate_pfx_package,
    generate_private_key,
)

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

    _stored = StoredState()

    def __init__(self, *args):
        """Initializes all events that need to be observed."""
        super().__init__(*args)
        self.certificates = TLSCertificatesRequires(self, "certificates")
        self.cert_admin_operator = CertAdminOperatorProvides(self, "cert-admin-operator")
        self.cert_certifier = CertCertifierProvides(self, "cert-certifier")
        self.cert_controller = CertControllerProvides(self, "cert-controller")
        self.cert_bootstrapper = CertBootstrapperProvides(self, "cert-bootstrapper")
        self._container_name = self._service_name = "magma-orc8r-certifier"
        self.provided_relation_name = list(self.meta.provides.keys())[0]
        self._container = self.unit.get_container(self._container_name)
        self._db = pgsql.PostgreSQLClient(self, "db")
        self._stored.set_default(admin_operator_password="")
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

    @property
    def _root_certs_are_stored(self) -> bool:
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
    def _application_certs_are_stored(self) -> bool:
        """Returns whether application certificate are stored.

        Returns:
            bool: Whether application certificate are stored.
        """
        return (
            self._container.exists(f"{self.BASE_CERTS_PATH}/admin_operator.pem")
            and self._container.exists(  # noqa: W503
                f"{self.BASE_CERTS_PATH}/admin_operator.key.pem"
            )
            and self._container.exists(f"{self.BASE_CERTS_PATH}/admin_operator.pfx")  # noqa: W503
            and self._container.exists(f"{self.BASE_CERTS_PATH}/certifier.pem")  # noqa: W503
            and self._container.exists(f"{self.BASE_CERTS_PATH}/certifier.key")  # noqa: W503
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
            )
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
    def _domain_config_is_valid(self) -> bool:
        """Returns whether the "domain" config is valid.

        For now simply checks if the config is set as a non-null value.

        Returns:
            bool: Whether the domain is a valid one.
        """
        domain = self.model.config.get("domain")
        if not domain:
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
        if not self._domain_config_is_valid:
            self.unit.status = BlockedStatus("Config 'domain' is not valid")
            event.defer()
            return
        self._write_metricsd_config_file()
        self._generate_application_certificates()

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
            logger.warning("Config 'domain' not valid")
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
        if not self._root_certs_are_stored:
            self.unit.status = WaitingStatus("Waiting for certs to be available")
            event.defer()
            return
        if not self._application_certs_are_stored:
            self.unit.status = WaitingStatus("Waiting for certs to be available")
            event.defer()
            return
        self._configure_magma_orc8r_certifier(event)

    def _on_certificates_relation_joined(self, event: RelationJoinedEvent) -> None:
        """Juju event triggered when pebble is ready.

        Args:
            event: Juju event

        Returns:
            None
        """
        domain_name = self.model.config.get("domain")
        if not self._domain_config_is_valid:
            logger.info("Domain config is not valid")
            event.defer()
            return
        self.certificates.request_certificate(
            cert_type="server",
            common_name=f"*.{domain_name}",
        )

    def _on_certificate_available(self, event: CertificateAvailableEvent) -> None:
        """Runs whenever the certificates available event is triggered.

        Pushes the certificates retrieved from the relation data to the workload container.

        Args:
            event (CertificateAvailableEvent): Custom Juju event for certificate available.

        Returns:
            None
        """
        logger.info("Certificate is available")
        if not self._container.can_connect():
            logger.info("Cant connect to container - Won't push certificates to workload")
            event.defer()
            return
        certificate_data = event.certificate_data
        if not self._root_certs_are_stored:
            logger.info("Pushing controller certificate to workload")
            self._container.push(
                path=f"{self.BASE_CERTS_PATH}/rootCA.pem", source=certificate_data["ca"]
            )
            self._container.push(
                path=f"{self.BASE_CERTS_PATH}/controller.crt", source=certificate_data["cert"]
            )
            self._container.push(
                path=f"{self.BASE_CERTS_PATH}/controller.key", source=certificate_data["key"]
            )
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

    def _write_metricsd_config_file(self) -> None:
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
        """Generates application certificates and pushes them to the workload container.

        The following certificates/keys are created:
            - certifier.pem
            - certifier.key
            - admin_operator.pem
            - admin_operator.key.pem
            - admin_operator.pfx

        Returns:
            None
        """
        logger.info("Generating Application Certificates")
        certifier_key = generate_private_key()
        certifier_pem = generate_ca(
            private_key=certifier_key,
            subject=f"certifier.{self.model.config['domain']}",
        )
        admin_operator_key_pem = generate_private_key()
        admin_operator_csr = generate_csr(
            private_key=admin_operator_key_pem,
            subject="admin_operator",
        )
        admin_operator_pem = generate_certificate(
            csr=admin_operator_csr,
            ca=certifier_pem,
            ca_key=certifier_key,
        )
        password = self._generate_password()
        admin_operator_pfx = generate_pfx_package(
            private_key=admin_operator_key_pem,
            certificate=admin_operator_pem,
            password=password,
        )
        bootstrapper_key = generate_private_key()
        self._container.push(path=f"{self.BASE_CERTS_PATH}/certifier.pem", source=certifier_pem)
        self._container.push(path=f"{self.BASE_CERTS_PATH}/certifier.key", source=certifier_key)
        self._container.push(
            path=f"{self.BASE_CERTS_PATH}/admin_operator.pem", source=admin_operator_pem
        )
        self._container.push(
            path=f"{self.BASE_CERTS_PATH}/admin_operator.key.pem", source=admin_operator_key_pem
        )
        self._container.push(
            path=f"{self.BASE_CERTS_PATH}/admin_operator.pfx", source=admin_operator_pfx
        )
        self._container.push(
            path=f"{self.BASE_CERTS_PATH}/bootstrapper.key", source=bootstrapper_key
        )
        self._stored.admin_operator_password = password

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
        event.set_results(
            {
                "password": self._stored.admin_operator_password,
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
            certificate=certificate_string,  # type: ignore[arg-type]
            private_key=private_key_string,  # type: ignore[arg-type]
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
            certificate=certificate_string,  # type: ignore[arg-type]
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
            certificate=certificate_string,  # type: ignore[arg-type]
            private_key=private_key_string,  # type: ignore[arg-type]
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
            logger.info("Certificate 'controller' not yet available")
            event.defer()
            return
        private_key_string = private_key.read()
        self.cert_bootstrapper.set_private_key(
            relation_id=event.relation_id,
            private_key=private_key_string,  # type: ignore[arg-type]
        )


if __name__ == "__main__":
    main(MagmaOrc8rCertifierCharm)
