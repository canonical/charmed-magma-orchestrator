#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import ops.lib
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from charms.tls_certificates_interface.v0.tls_certificates import (
    CertificatesRequirerCharmEvents,
    InsecureCertificatesRequires,
)
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer
from pgconnstr import ConnectionString  # type: ignore[import]

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

    # BASE_CERTS_PATH_OBJECT = Path(BASE_CERTS_PATH)
    # CERTIFIER_CERT_PATH_OBJECT = BASE_CERTS_PATH_OBJECT / "certifier.pem"
    # CERTIFIER_KEY_PATH_OBJECT = BASE_CERTS_PATH_OBJECT / "certifier.key"

    on = CertificatesRequirerCharmEvents()

    def __init__(self, *args):
        """An instance of this object everytime an event occurs."""
        super().__init__(*args)

        self.certificates = InsecureCertificatesRequires(self, "certificates")
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
        self.framework.observe(self.on.certificate_available, self._on_certificate_available)
        self.framework.observe(self.on.certificates_relation_joined, self._on_relation_joined)

    def _on_relation_joined(self, event):
        domain_name = self.model.config["domain"]
        self.certificates.request_certificate(
            cert_type="server",
            common_name=domain_name,
        )

    def _on_certificate_available(self, event):
        logger.info("Certificate is available")
        if not self._container.can_connect():
            logger.info("Cant connect to container - Won't push certificates to workload")
            event.defer()
            return
        certificate_data = event.certificate_data
        if certificate_data["common_name"] == self.model.config["domain"]:
            logger.info("Pushing certificate to workload")
            self._container.push(f"{self.BASE_CERTS_PATH}/certifier.pem", certificate_data["cert"])
            self._container.push(f"{self.BASE_CERTS_PATH}/certifier.key", certificate_data["key"])

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
        """Triggered when pebble is ready."""
        if not self._domain_config_is_valid:
            self.unit.status = BlockedStatus("Config 'domain' is not valid")
            logger.warning("Config 'domain' not valid")
            event.defer()
            return
        if not self._db_relations_created:
            self.unit.status = BlockedStatus("Waiting for database relation to be created")
            event.defer()
            return
        if not self._certificates_relations_created:
            self.unit.status = BlockedStatus("Waiting for certificates relation to be created")
            event.defer()
            return
        if not self._db_relation_established:
            self.unit.status = WaitingStatus("Waiting for database relation to be established")
            event.defer()
            return
        if not self._certs_are_stored():
            self.unit.status = WaitingStatus("Waiting for certs to be available")
            event.defer()
            return
        self._configure_magma_orc8r_certifier(event)

    def _on_config_changed(self, event):
        if not self._domain_config_is_valid:
            self.unit.status = BlockedStatus("Config 'domain' is not valid")
            logger.warning("Config 'domain' not valid")
            event.defer()
            return

    def _certs_are_stored(self) -> bool:
        return self._container.exists(
            f"{self.BASE_CERTS_PATH}/certifier.pem"
        ) and self._container.exists(f"{self.BASE_CERTS_PATH}/certifier.key")

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
    def _db_relations_created(self) -> bool:
        return self._relation_created("db")

    @property
    def _certificates_relations_created(self) -> bool:
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
            self.unit.status = MaintenanceStatus("Configuring pod")
            plan = self._container.get_plan()
            layer = self._pebble_layer
            if plan.services != layer.services:
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
                        f"-vpnc={self.BASE_CERTS_PATH}/vpn_ca.crt "
                        f"-vpnk={self.BASE_CERTS_PATH}/vpn_ca.key "
                        "-logtostderr=true "
                        "-v=0",
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
            return ConnectionString(db_relation.data[db_relation.app]["master"])
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
