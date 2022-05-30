#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import secrets
import string
import time

import ops.lib
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from charms.tls_certificates_interface.v0.tls_certificates import (
    CertificatesRequirerCharmEvents,
    InsecureCertificatesRequires,
)
from ops.charm import ActionEvent, CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import ExecError, Layer
from pgconnstr import ConnectionString  # type: ignore[import]

logger = logging.getLogger(__name__)
pgsql = ops.lib.use("pgsql", 1, "postgresql-charmers@lists.launchpad.net")


class MagmaNmsMagmalteCharm(CharmBase):

    DB_NAME = "magma_dev"
    GRAFANA_URL = "orc8r-user-grafana:3000"
    CERTIFICATE_COMMON_NAME = "admin_operator"
    BASE_CERTS_PATH = "/run/secrets"
    _stored = StoredState()

    on = CertificatesRequirerCharmEvents()

    def __init__(self, *args):
        """Creates a new instance of this object for each event."""
        super().__init__(*args)

        self._container_name = self._service_name = "magma-nms-magmalte"
        self._container = self.unit.get_container(self._container_name)
        self._stored.set_default(admin_username="", admin_password="")
        self._db = pgsql.PostgreSQLClient(self, "db")
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[("magmalte", 8081)],
            service_name="magmalte",
            additional_labels={
                "app.kubernetes.io/part-of": "magma",
                "app.kubernetes.io/component": "magmalte",
            },
        )
        self.certificates = InsecureCertificatesRequires(self, "certificates")
        self.framework.observe(
            self.on.magma_nms_magmalte_pebble_ready, self._on_magma_nms_magmalte_pebble_ready
        )
        self.framework.observe(
            self._db.on.database_relation_joined, self._on_database_relation_joined
        )
        self.framework.observe(
            self.on.get_admin_credentials_action, self._on_get_admin_credentials
        )
        self.framework.observe(
            self.on.create_nms_admin_user_action, self._create_nms_admin_user_action
        )
        self.framework.observe(
            self.on.certificates_relation_joined, self._on_certificates_relation_joined
        )
        self.framework.observe(self.on.certificate_available, self._on_certificate_available)

    def _on_certificates_relation_joined(self, event):
        self.certificates.request_certificate(
            cert_type="server",
            common_name=self.CERTIFICATE_COMMON_NAME,
        )

    def _on_certificate_available(self, event):
        logger.info("Certificate is available")
        if not self._container.can_connect():
            logger.info("Cant connect to container - Won't push certificates to workload")
            event.defer()
            return
        if self._certs_are_stored:
            logger.info("Certificates are already stored - Doing nothing")
            return
        certificate_data = event.certificate_data
        if certificate_data["common_name"] == self.CERTIFICATE_COMMON_NAME:
            logger.info("Pushing certificate to workload")
            self._container.push(
                f"{self.BASE_CERTS_PATH}/{self.CERTIFICATE_COMMON_NAME}.pem",
                certificate_data["cert"],
            )
            self._container.push(
                f"{self.BASE_CERTS_PATH}/{self.CERTIFICATE_COMMON_NAME}.key.pem",
                certificate_data["key"],
            )

    @property
    def _certs_are_stored(self) -> bool:
        return self._container.exists(
            f"{self.BASE_CERTS_PATH}/{self.CERTIFICATE_COMMON_NAME}.pem"
        ) and self._container.exists(
            f"{self.BASE_CERTS_PATH}/{self.CERTIFICATE_COMMON_NAME}.key.pem"
        )

    def _on_magma_nms_magmalte_pebble_ready(self, event):
        if not self._relations_ready:
            event.defer()
            return
        if not self._certs_are_stored:
            self.unit.status = WaitingStatus("Waiting for certs to be available")
            event.defer()
            return
        self._configure_pebble(event)
        self._create_master_nms_admin_user()

    def _create_master_nms_admin_user(self):
        username = self._get_admin_username()
        password = self._get_admin_password()
        start_time = time.time()
        timeout = 60
        while time.time() - start_time < timeout:
            try:
                self._create_nms_admin_user(username, password, "master")
                return
            except ExecError:
                logger.info("Failed to create admin user - Will retry in 5 seconds")
                time.sleep(5)
        message = "Timed out trying to create admin user for NMS"
        logger.info(message)
        raise TimeoutError(message)

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
        else:
            event.defer()

    def _configure_pebble(self, event):
        """Adds layer to pebble config if the proposed config is different from the current one."""
        if self._container.can_connect():
            plan = self._container.get_plan()
            layer = self._pebble_layer
            if plan.services != layer.services:
                self.unit.status = MaintenanceStatus(
                    f"Configuring pebble layer for {self._service_name}"
                )
                self._container.add_layer(self._container_name, layer, combine=True)
                self._container.restart(self._service_name)
                logger.info(f"Restarted container {self._service_name}")
                self.unit.status = ActiveStatus()
        else:
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()

    @property
    def _environment_variables(self) -> dict:
        return {
            "API_CERT_FILENAME": "/run/secrets/admin_operator.pem",
            "API_PRIVATE_KEY_FILENAME": "/run/secrets/admin_operator.key.pem",
            "API_HOST": f"orc8r-nginx-proxy.{self._namespace}.svc.cluster.local",
            "PORT": str(8081),
            "HOST": "0.0.0.0",
            "MYSQL_HOST": str(self._get_db_connection_string.host),
            "MYSQL_PORT": str(self._get_db_connection_string.port),
            "MYSQL_DB": self.DB_NAME,
            "MYSQL_USER": str(self._get_db_connection_string.user),
            "MYSQL_PASS": str(self._get_db_connection_string.password),
            "MAPBOX_ACCESS_TOKEN": "",
            "MYSQL_DIALECT": "postgres",
            "PUPPETEER_SKIP_DOWNLOAD": "true",
            "USER_GRAFANA_ADDRESS": self.GRAFANA_URL,
        }

    @property
    def _pebble_layer(self) -> Layer:
        """Returns pebble layer for the charm."""
        return Layer(
            {
                "summary": f"{self._service_name} pebble layer",
                "services": {
                    self._service_name: {
                        "override": "replace",
                        "startup": "enabled",
                        "command": f"/usr/local/bin/wait-for-it.sh -s -t 30 "
                        f"{self._get_db_connection_string.host}:"
                        f"{self._get_db_connection_string.port} "
                        f"-- yarn run start:prod",
                        "environment": self._environment_variables,
                    }
                },
            }
        )

    def _create_nms_admin_user_action(self, event):
        self._create_nms_admin_user(
            email=event.params["email"],
            password=event.params["password"],
            organization=event.params["organization"],
        )

    def _on_get_admin_credentials(self, event: ActionEvent) -> None:
        if not self._relations_ready:
            event.fail("Relations aren't yet set up. Please try again in a few minutes")
            return

        event.set_results(
            {
                "admin-username": self._get_admin_username(),
                "admin-password": self._get_admin_password(),
            }
        )

    def _create_nms_admin_user(self, email: str, password: str, organization: str):
        """
        Creates Admin user for the master organization in NMS.
        """
        logger.info("Creating admin user for NMS")
        process = self._container.exec(
            [
                "/usr/local/bin/yarn",
                "setAdminPassword",
                organization,
                email,
                password,
            ],
            timeout=30,
            environment=self._environment_variables,
            working_dir="/usr/src/packages/magmalte",
        )
        try:
            process.wait_output()
        except ExecError as e:
            logger.error("Exited with code %d. Stderr:", e.exit_code)
            for line in e.stderr.splitlines():
                logger.error("    %s", line)
            raise e
        logger.info("Successfully created admin user")

    @property
    def _relations_ready(self) -> bool:
        """Checks whether required relations are ready."""
        required_relations = ["certificates", "db"]
        if missing_relations := [
            relation for relation in required_relations if not self.model.get_relation(relation)
        ]:
            self.unit.status = BlockedStatus(
                f"Waiting for relation(s) to be created: {', '.join(missing_relations)}"
            )
            return False
        if not self._get_db_connection_string:
            self.unit.status = WaitingStatus("Waiting for database relation to be established")
            return False
        return True

    @property
    def _get_db_connection_string(self):
        """Returns DB connection string provided by the DB relation."""
        try:
            db_relation = self.model.get_relation("db")
            return ConnectionString(db_relation.data[db_relation.app]["master"])  # type: ignore[index, union-attr]  # noqa: E501
        except (AttributeError, KeyError):
            return None

    @property
    def _namespace(self) -> str:
        """Returns the namespace."""
        return self.model.name

    def _get_admin_password(self) -> str:
        """Returns the password for the admin user."""
        if not self._stored.admin_password:
            self._stored.admin_password = self._generate_password()
        return self._stored.admin_password

    def _get_admin_username(self) -> str:
        """Returns the admin user."""
        if not self._stored.admin_username:
            self._stored.admin_username = "admin@juju.com"
        return self._stored.admin_username

    @staticmethod
    def _generate_password() -> str:
        """Generates a random 12 character password."""
        chars = string.ascii_letters + string.digits
        return "".join(secrets.choice(chars) for _ in range(12))


if __name__ == "__main__":
    main(MagmaNmsMagmalteCharm)
