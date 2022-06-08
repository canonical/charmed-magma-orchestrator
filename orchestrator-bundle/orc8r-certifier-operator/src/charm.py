#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import ops.lib
from charms.magma_orc8r_certifier.v0.cert_admin_operator import (
    CertAdminOperatorProvides,
)
from charms.magma_orc8r_certifier.v0.cert_certifier import CertCertifierProvides
from charms.magma_orc8r_certifier.v0.cert_controller import CertControllerProvides
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from charms.tls_certificates_interface.v0.tls_certificates import (
    InsecureCertificatesRequires,
)
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
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

    DB_NAME = "magma_dev"
    BASE_CONFIG_PATH = "/var/opt/magma/configs/orc8r"
    BASE_CERTS_PATH = "/var/opt/magma/certs"

    # TODO: The various URL's should be provided through relationships
    PROMETHEUS_URL = "http://orc8r-prometheus:9090"
    PROMETHEUS_CONFIGURER_URL = "http://orc8r-prometheus:9100"
    ALERTMANAGER_URL = "http://orc8r-alertmanager:9093"
    ALERTMANAGER_CONFIGURER_URL = "http://orc8r-alertmanager:9101"

    def __init__(self, *args):
        """An instance of this object everytime an event occurs."""
        super().__init__(*args)

        self.certificates = InsecureCertificatesRequires(self, "certificates")
        self.cert_admin_operator = CertAdminOperatorProvides(self, "cert-admin-operator")
        self.cert_certifier = CertCertifierProvides(self, "cert-certifier")
        self.cert_controller = CertControllerProvides(self, "cert-controller")
        self._container_name = self._service_name = "magma-orc8r-certifier"
        self._container = self.unit.get_container(self._container_name)
        self._db = pgsql.PostgreSQLClient(self, "db")
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[("grpc", 9180, 9086)],
            additional_labels={
                "app.kubernetes.io/part-of": "orc8r-app",
                "orc8r.io/analytics_collector": "true",
            },
        )
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(
            self.on.magma_orc8r_certifier_pebble_ready, self._on_magma_orc8r_certifier_pebble_ready
        )
        self.framework.observe(
            self._db.on.database_relation_joined, self._on_database_relation_joined
        )
        self.framework.observe(
            self.certificates.on.certificate_available, self._on_certificate_available
        )
        self.framework.observe(
            self.on.certificates_relation_joined, self._on_certificates_relation_joined
        )
        self.framework.observe(
            self.cert_admin_operator.on.certificate_request,
            self._on_admin_operator_certificate_request,
        )
        self.framework.observe(
            self.cert_certifier.on.certificate_request, self._on_certifier_certificate_request
        )
        self.framework.observe(
            self.cert_controller.on.certificate_request, self._on_controller_certificate_request
        )

    def _on_admin_operator_certificate_request(self, event):
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

    def _on_certifier_certificate_request(self, event):
        if not self._container.can_connect():
            logger.info("Container not yet available")
            event.defer()
            return
        try:
            certificate = self._container.pull(path=f"{self.BASE_CERTS_PATH}/certifier.pem")
        except ops.pebble.PathError:
            logger.info("Certificate 'certifier not' yet available")
            event.defer()
            return
        certificate_string = certificate.read()
        self.cert_certifier.set_certificate(
            relation_id=event.relation_id,
            certificate=certificate_string,  # type: ignore[arg-type]
        )

    def _on_controller_certificate_request(self, event):
        if not self._container.can_connect():
            logger.info("Container not yet available")
            event.defer()
            return
        try:
            certificate = self._container.pull(path=f"{self.BASE_CERTS_PATH}/controller.crt")
            private_key = self._container.pull(path=f"{self.BASE_CERTS_PATH}/controller.key")
        except ops.pebble.PathError:
            logger.info("Certificate 'controller not' yet available")
            event.defer()
            return
        certificate_string = certificate.read()
        private_key_string = private_key.read()
        self.cert_controller.set_certificate(
            relation_id=event.relation_id,
            certificate=certificate_string,  # type: ignore[arg-type]
            private_key=private_key_string,  # type: ignore[arg-type]
        )

    def _on_certificates_relation_joined(self, event):
        domain_name = self.model.config.get("domain")
        if not self._domain_config_is_valid:
            logger.info("Domain config is not valid")
            event.defer()
            return
        self.certificates.request_certificate(
            cert_type="server",
            common_name=f"*.{domain_name}",
        )

    def _on_certificate_available(self, event):
        logger.info("Certificate is available")
        domain_name = self.model.config["domain"]
        if not self._container.can_connect():
            logger.info("Cant connect to container - Won't push certificates to workload")
            event.defer()
            return
        certificate_data = event.certificate_data
        if not self._ca_is_stored:
            logger.info("Pushing CA certificate to workload")
            self._container.push(f"{self.BASE_CERTS_PATH}/rootCA.pem", certificate_data["ca"])
        if self._root_certs_are_stored:
            logger.info("Certificates are already stored - Not doing anything")
            return
        if certificate_data["common_name"] == f"*.{domain_name}":
            logger.info("Pushing controller certificate to workload")
            self._container.push(
                path=f"{self.BASE_CERTS_PATH}/controller.crt", source=certificate_data["cert"]
            )
            self._container.push(
                path=f"{self.BASE_CERTS_PATH}/controller.key", source=certificate_data["key"]
            )
        if self._root_certs_are_stored and not self._application_certs_are_stored:
            self._generate_application_certificates()
        self._on_magma_orc8r_certifier_pebble_ready(event)

    def _write_metricsd_config_file(self):
        metricsd_config = (
            f'prometheusQueryAddress: "{self.PROMETHEUS_URL}"\n'
            f'alertmanagerApiURL: "{self.ALERTMANAGER_URL}/api/v2"\n'
            f'prometheusConfigServiceURL: "{self.PROMETHEUS_CONFIGURER_URL}/v1"\n'
            f'alertmanagerConfigServiceURL: "{self.ALERTMANAGER_CONFIGURER_URL}/v1"\n'
            '"profile": "prometheus"\n'
        )
        self._container.push(f"{self.BASE_CONFIG_PATH}/metricsd.yml", metricsd_config)

    def _on_install(self, event):
        """Runs each time the charm is installed."""
        if not self._container.can_connect():
            event.defer()
            return
        self._write_metricsd_config_file()

    def _on_magma_orc8r_certifier_pebble_ready(self, event):
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
            self.unit.status = BlockedStatus("Waiting for certificates relation to be created")
            event.defer()
            return
        if not self._db_relation_established:
            self.unit.status = WaitingStatus("Waiting for database relation to be established")
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

    def _generate_application_certificates(self):
        """
        Generates admin operator certificates.
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
        admin_operator_pfx = generate_pfx_package(
            private_key=admin_operator_key_pem,
            certificate=admin_operator_pem,
            password=self.model.config["passphrase"],
        )
        self._container.push(f"{self.BASE_CERTS_PATH}/certifier.pem", certifier_pem)
        self._container.push(f"{self.BASE_CERTS_PATH}/certifier.key", certifier_key)
        self._container.push(f"{self.BASE_CERTS_PATH}/admin_operator.pem", admin_operator_pem)
        self._container.push(
            f"{self.BASE_CERTS_PATH}/admin_operator.key.pem", admin_operator_key_pem
        )
        self._container.push(f"{self.BASE_CERTS_PATH}/admin_operator.pfx", admin_operator_pfx)

    @property
    def _root_certs_are_stored(self) -> bool:
        return (
            self._container.exists(f"{self.BASE_CERTS_PATH}/controller.crt")
            and self._container.exists(f"{self.BASE_CERTS_PATH}/controller.key")  # noqa: W503
        )

    @property
    def _application_certs_are_stored(self) -> bool:
        return (
            self._container.exists(f"{self.BASE_CERTS_PATH}/admin_operator.pem")
            and self._container.exists(  # noqa: W503, E501
                f"{self.BASE_CERTS_PATH}/admin_operator.key.pem"
            )
            and self._container.exists(f"{self.BASE_CERTS_PATH}/admin_operator.pfx")  # noqa: W503
            and self._container.exists(f"{self.BASE_CERTS_PATH}/certifier.pem")  # noqa: W503
            and self._container.exists(f"{self.BASE_CERTS_PATH}/certifier.key")  # noqa: W503
        )

    @property
    def _ca_is_stored(self):
        return self._container.exists(f"{self.BASE_CERTS_PATH}/rootCA.pem")

    def _on_database_relation_joined(self, event):
        """
        Event handler for database relation change.
        - Sets the event.database field on the database joined event.
        - Required because setting the database name is only possible
          from inside the event handler per https://github.com/canonical/ops-lib-pgsql/issues/2
        - Sets our database parameters based on what was provided
          in the relation event.
        """
        if self.unit.is_leader():
            event.database = self.DB_NAME

    @property
    def _db_relation_created(self) -> bool:
        return self._relation_created("db")

    @property
    def _certificates_relation_created(self) -> bool:
        return self._relation_created("certificates")

    def _relation_created(self, relation_name: str) -> bool:
        if not self.model.get_relation(relation_name):
            return False
        return True

    @property
    def _db_relation_established(self) -> bool:
        """Validates that database relation is established (that there is a relation and that
        credentials have been passed)."""
        if not self._get_db_connection_string:
            return False
        return True

    def _configure_magma_orc8r_certifier(self, event):
        """Adds layer to pebble config if the proposed config is different from the current one."""
        if self._container.can_connect():
            plan = self._container.get_plan()
            layer = self._pebble_layer
            if plan.services != layer.services:
                self.unit.status = MaintenanceStatus("Configuring pod")
                self._container.add_layer(self._container_name, layer, combine=True)
                self._container.restart(self._service_name)
                logger.info(f"Restarted container {self._service_name}")
                self.unit.status = ActiveStatus()
        else:
            self.unit.status = WaitingStatus("Waiting for container to be ready...")
            event.defer()

    @property
    def _pebble_layer(self) -> Layer:
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
                        "-logtostderr=true " "-v=0",
                        "environment": {
                            "DATABASE_SOURCE": f"dbname={self.DB_NAME} "
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
    def _get_db_connection_string(self):
        """Returns DB connection string provided by the DB relation."""
        try:
            db_relation = self.model.get_relation("db")
            return ConnectionString(db_relation.data[db_relation.app]["master"])  # type: ignore[index, union-attr]  # noqa: E501
        except (AttributeError, KeyError):
            return None

    @property
    def _domain_config_is_valid(self) -> bool:
        domain = self.model.config.get("domain")
        if not domain:
            return False
        return True

    @property
    def _namespace(self) -> str:
        return self.model.name


if __name__ == "__main__":
    main(MagmaOrc8rCertifierCharm)
