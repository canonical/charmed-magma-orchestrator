#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""magma-nms-magmalte.

Magmalte is a microservice built using express framework. It contains set of application and
router level middlewares. It uses sequelize ORM to connect to the NMS DB for servicing any
routes involving DB interaction.
"""

import logging
import secrets
import string
import time
from typing import Optional, Union

import ops.lib
import psycopg2  # type: ignore[import]
from charms.grafana_k8s.v0.grafana_auth import (
    GrafanaAuthProxyProvider,
    UrlsAvailableEvent,
)
from charms.magma_orc8r_certifier.v0.cert_admin_operator import (
    CertAdminOperatorRequires,
    CertificateAvailableEvent,
)
from charms.observability_libs.v1.kubernetes_service_patch import (
    KubernetesServicePatch,
    ServicePort,
)
from ops.charm import (
    ActionEvent,
    CharmBase,
    PebbleReadyEvent,
    RelationBrokenEvent,
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
from ops.pebble import ExecError, Layer
from pgconnstr import ConnectionString  # type: ignore[import]

logger = logging.getLogger(__name__)
pgsql = ops.lib.use("pgsql", 1, "postgresql-charmers@lists.launchpad.net")


class ServiceNotRunningError(Exception):
    """Custom error that can be raised if container service is not running."""

    pass


class MagmaNmsMagmalteCharm(CharmBase):
    """Main class that is instantiated everytime an event occurs."""

    DB_NAME = "magma_dev"
    GRAFANA_AUTH_RELATION = "grafana-auth"
    BASE_CERTS_PATH = "/run/secrets"
    NMS_ADMIN_USERNAME = "admin@juju.com"
    CERT_ADMIN_OPERATOR_RELATION = "cert-admin-operator"
    NMS_MAGMALTE_K8S_SERVICE_NAME = "magmalte"
    NMS_MAGMALTE_K8S_SERVICE_PORT = 8081

    def __init__(self, *args):
        """Initializes all event that need to be observed."""
        super().__init__(*args)
        self._container_name = self._service_name = "magma-nms-magmalte"
        self._container = self.unit.get_container(self._container_name)
        self._db = pgsql.PostgreSQLClient(self, "db")
        self.admin_operator = CertAdminOperatorRequires(self, self.CERT_ADMIN_OPERATOR_RELATION)
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[
                ServicePort(
                    name=self.NMS_MAGMALTE_K8S_SERVICE_NAME,
                    port=self.NMS_MAGMALTE_K8S_SERVICE_PORT,
                )
            ],
            service_name=self.NMS_MAGMALTE_K8S_SERVICE_NAME,
            additional_labels={
                "app.kubernetes.io/part-of": "magma",
                "app.kubernetes.io/component": self.NMS_MAGMALTE_K8S_SERVICE_NAME,
            },
        )
        self._grafana_auth_provider = GrafanaAuthProxyProvider(
            self, auto_sign_up=False, relation_name=self.GRAFANA_AUTH_RELATION
        )
        self.framework.observe(
            self.on.magma_nms_magmalte_pebble_ready, self._on_magma_nms_magmalte_pebble_ready
        )
        self.framework.observe(
            self._db.on.database_relation_joined, self._on_database_relation_joined
        )
        self.framework.observe(self.on.db_relation_broken, self._on_database_relation_broken)
        self.framework.observe(
            self.on.magma_nms_magmalte_relation_joined,
            self._on_magma_nms_magmalte_relation_joined,
        )
        self.framework.observe(
            self.on.get_master_admin_credentials_action, self._on_get_master_admin_credentials
        )
        self.framework.observe(
            self.on.create_nms_admin_user_action, self._create_nms_admin_user_action
        )
        self.framework.observe(
            self.admin_operator.on.certificate_available, self._on_certificate_available
        )
        self.framework.observe(
            self._grafana_auth_provider.on.urls_available, self._on_grafana_urls_available
        )
        self.framework.observe(
            self.on[self.GRAFANA_AUTH_RELATION].relation_broken, self._on_grafana_relation_broken
        )

    @property
    def _certs_are_stored(self) -> bool:
        """Returns whether the bootstrapper admin operator certificates are stored.

        Returns:
            bool: True/False
        """
        return self._container.exists(
            f"{self.BASE_CERTS_PATH}/admin_operator.pem"
        ) and self._container.exists(f"{self.BASE_CERTS_PATH}/admin_operator.key.pem")

    @property
    def _service_is_running(self) -> bool:
        """Retrieves the workload service and returns whether it is running.

        Returns:
            bool: Whether service is running
        """
        if self._container.can_connect():
            try:
                self._container.get_service(self._service_name)
                return True
            except ModelError:
                pass
        return False

    @property
    def _environment_variables(self) -> dict:
        """Returns environment variables necessary for running the workload service.

        Returns:
            dict: Environment variables
        """
        if not self._get_db_connection_string:
            raise ValueError("DB Connection string not yet available from relation data.")
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
            "USER_GRAFANA_ADDRESS": self._grafana_url,
        }

    @property
    def _pebble_layer(self) -> Layer:
        """Returns pebble layer for the charm.

        Returns:
            Layer: Pebble Layer
        """
        if not self._get_db_connection_string:
            raise ValueError("DB Connection string not yet available from relation data.")
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
    def _get_db_connection_string(self) -> Optional[ConnectionString]:
        """Returns DB connection string provided by the DB relation.

        Returns:
            ConnectionString: pgconnstr ConnectionString object.
        """
        try:
            db_relation = self.model.get_relation("db")
            return ConnectionString(db_relation.data[db_relation.app]["master"])  # type: ignore[union-attr, index]  # noqa: E501
        except (AttributeError, KeyError):
            return None

    @property
    def _namespace(self) -> str:
        """Returns the namespace.

        Returns:
            str: Kubernetes namespace.
        """
        return self.model.name

    @property
    def _db_relation_created(self) -> bool:
        """Returns whether db relation is created.

        Returns:
            bool: True/False
        """
        return self._relation_created("db")

    @property
    def _cert_admin_operator_relation_created(self) -> bool:
        """Returns whether cert-admin-operator relation is created.

        Returns:
            bool: True/False
        """
        return self._relation_created(self.CERT_ADMIN_OPERATOR_RELATION)

    @property
    def _grafana_auth_relation_created(self) -> bool:
        """Returns whether grafana-auth relation is created.

        Returns:
            bool: True/False
        """
        return self._relation_created(self.GRAFANA_AUTH_RELATION)

    def _relation_created(self, relation_name: str) -> bool:
        """Returns whether given relation was created.

        Args:
            relation_name (str): Relation name

        Returns:
            bool: True/False
        """
        try:
            if self.model.get_relation(relation_name):
                return True
            return False
        except KeyError:
            return False

    def _on_certificate_available(self, event: CertificateAvailableEvent) -> None:
        """Triggered when admin operator certificates are available from relation data.

        Args:
            event (CertificateAvailableEvent): Event for whenever certificates are available.

        Returns:
            None
        """
        logger.info("Admin Operator certificate available")
        if not self._container.can_connect():
            logger.info("Can't connect to container - Deferring")
            event.defer()
            return
        self._container.push(
            path=f"{self.BASE_CERTS_PATH}/admin_operator.pem", source=event.certificate
        )
        self._container.push(
            path=f"{self.BASE_CERTS_PATH}/admin_operator.key.pem", source=event.private_key
        )
        self._on_magma_nms_magmalte_pebble_ready(event)

    def _on_magma_nms_magmalte_pebble_ready(
        self,
        event: Union[
            PebbleReadyEvent, CertificateAvailableEvent, UrlsAvailableEvent, RelationJoinedEvent
        ],
    ) -> None:
        """Configures pebble layer and creates admin user of nms-magmalte.

        Args:
            event (
            PebbleReadyEvent, CertificateAvailableEvent, UrlsAvailableEvent, RelationJoinedEvent
            ): Juju event

        Returns:
            None
        """
        if not self._db_relation_created:
            self.unit.status = BlockedStatus("Waiting for db relation to be created")
            event.defer()
            return
        if not self._cert_admin_operator_relation_created:
            self.unit.status = BlockedStatus(
                f"Waiting for {self.CERT_ADMIN_OPERATOR_RELATION} relation to be created"
            )
            event.defer()
            return
        if not self._grafana_auth_relation_created:
            self.unit.status = BlockedStatus(
                f"Waiting for {self.GRAFANA_AUTH_RELATION} relation to be created"
            )
            event.defer()
            return
        if not self._db_relation_established:
            self.unit.status = WaitingStatus("Waiting for db relation to be ready")
            event.defer()
            return
        if not self._certs_are_stored:
            self.unit.status = WaitingStatus("Waiting for certs to be available")
            event.defer()
            return
        if not self._grafana_url:
            self.unit.status = WaitingStatus("Grafana url not yet available from relation data.")
            event.defer()
            return
        self._configure_pebble(event)
        if self.unit.is_leader():
            self._create_master_nms_admin_user()
        self.unit.status = ActiveStatus()

    def _create_master_nms_admin_user(self) -> None:
        """Creates NMS admin user.

        Returns:
            None
        """
        if not self._admin_password:
            self._create_admin_password()
        start_time = time.time()
        timeout = 60
        while time.time() - start_time < timeout:
            try:
                if self._admin_password:
                    self._create_nms_admin_user(
                        self.NMS_ADMIN_USERNAME, self._admin_password, "master"
                    )
                else:
                    logger.error(
                        "Admin password not present after creating it. This should never happen."
                    )
                return
            except (ExecError, ServiceNotRunningError):
                logger.info("Failed to create admin user - Will retry in 5 seconds")
                time.sleep(5)
        message = "Timed out trying to create admin user for NMS"
        logger.info(message)
        raise TimeoutError(message)

    def _on_database_relation_joined(self, event: RelationJoinedEvent) -> None:
        """Event handler for database relation change.

        - Sets the event.database field on the database joined event.
        - Required because setting the database name is only possible
          from inside the event handler per https://github.com/canonical/ops-lib-pgsql/issues/2
        - Sets our database parameters based on what was provided
          in the relation event.

        Args:
            event (RelationJoinedEvent): Juju event

        Returns:
            None
        """
        if not self.unit.is_leader():
            return
        event.database = self.DB_NAME  # type: ignore[attr-defined]
        self._on_magma_nms_magmalte_pebble_ready(event)

    def _on_database_relation_broken(self, event: RelationBrokenEvent):
        """Event handler for database relation broken.

        Args:
            event (RelationBrokenEvent): Juju event
        Returns:
            None
        """
        self.unit.status = BlockedStatus("Waiting for db relation to be created")

    def _on_magma_nms_magmalte_relation_joined(self, event: RelationJoinedEvent) -> None:
        """Triggered when requirers join the nms_magmalte relation.

        Args:
            event (RelationJoinedEvent): Juju event

        Returns:
            None
        """
        self._update_relations()
        if not self._service_is_running:
            event.defer()
            return

    def _update_relation_active_status(self, relation: Relation, is_active: bool) -> None:
        """Updates the relation data with the active status.

        Args:
            relation (Relation): Juju relation
            is_active (bool): Whether workload service is active.

        Returns:
            None
        """
        relation.data[self.unit].update(
            {
                "active": str(is_active),
            }
        )

    def _publish_nms_magmalte_k8s_service_details(self, relation: Relation) -> None:
        """Publishes the details of the nms-magmalte Kubertnetes service.

        Args:
            relation (Relation): Juju relation
        """
        relation.data[self.unit].update(
            {
                "k8s_service_name": self.NMS_MAGMALTE_K8S_SERVICE_NAME,
                "k8s_service_port": str(self.NMS_MAGMALTE_K8S_SERVICE_PORT),
            }
        )

    def _configure_pebble(
        self,
        event: Union[
            PebbleReadyEvent, CertificateAvailableEvent, UrlsAvailableEvent, RelationJoinedEvent
        ],
    ) -> None:
        """Configures pebble layer.

        Args:
            event (PebbleReadyEvent): Juju event

        Returns:
            None
        """
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
            logger.info(f"Restarted service {self._service_name}")
            self._update_relations()
        else:
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()

    def _update_relations(self) -> None:
        """Updates nms_magmalte relation with the workload service status.

        Returns:
            None
        """
        if not self.unit.is_leader():
            return
        relations = self.model.relations[self.meta.name]
        for relation in relations:
            self._publish_nms_magmalte_k8s_service_details(relation)
            self._update_relation_active_status(
                relation=relation, is_active=self._service_is_running
            )

    def _create_nms_admin_user_action(self, event: ActionEvent):
        if not self.unit.is_leader():
            event.fail("This action needs to be run on the leader")
            return
        self._create_nms_admin_user(
            email=event.params["email"],
            password=event.params["password"],
            organization=event.params["organization"],
        )

    def _on_get_master_admin_credentials(self, event: ActionEvent) -> None:
        try:
            self._container.get_service(self._service_name)
            if not self.model.get_relation("replicas"):
                event.fail("Peer relation not created yet")
                return
            if not self._admin_password:
                event.fail("Admin credentials have not been created yet")
                return
            event.set_results(
                {
                    "admin-username": self.NMS_ADMIN_USERNAME,
                    "admin-password": self._admin_password,
                }
            )
        except (ops.model.ModelError, ops.pebble.ConnectionError):
            event.fail("Workload service is not yet running")
            return
        except Exception as e:
            event.fail(str(e))
            return

    def _create_nms_admin_user(self, email: str, password: str, organization: str) -> None:
        """Creates Admin user for the master organization in NMS.

        Args:
            email (str): New user email/login username
            password (str): Password
            organization (str): Magma organization

        Returns:
            None
        """
        if not self._service_is_running:
            message = "Service should be running for the user to be created"
            logger.error(message)
            raise ServiceNotRunningError(message)

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
            for line in e.stderr.splitlines():  # type: ignore[union-attr]
                logger.error("    %s", line)
            raise e
        logger.info("Successfully created admin user")

    @property
    def _admin_password(self) -> Optional[str]:
        """Returns the password for the admin user.

        Returns:
            str: Password
        """
        app_data = self.model.get_relation("replicas").data[self.app]  # type: ignore[union-attr]
        if not app_data.get("admin_password"):
            return None
        return app_data.get("admin_password")

    def _create_admin_password(self) -> None:
        """Creates the password for the admin user.

        Returns:
            str: Password
        """
        app_data = self.model.get_relation("replicas").data[self.app]  # type: ignore[union-attr]
        app_data.update({"admin_password": self._generate_password()})

    @staticmethod
    def _generate_password() -> str:
        """Generates a random 12 character password.

        Returns:
            str: Password
        """
        chars = string.ascii_letters + string.digits
        return "".join(secrets.choice(chars) for _ in range(12))

    def _on_grafana_urls_available(self, event: UrlsAvailableEvent):
        """Triggered when grafana urls are available from relation data.

        Args:
            event: UrlsAvailableEvent.
        """
        app_data = self.model.get_relation("replicas").data[self.app]  # type: ignore[union-attr]  # noqa: E501
        app_data.update({"grafana_url": event.urls[0]})
        self._on_magma_nms_magmalte_pebble_ready(event)

    def _on_grafana_relation_broken(self, event: RelationBrokenEvent):
        self.unit.status = BlockedStatus("Waiting for grafana relation to be created")

    @property
    def _grafana_url(self) -> Optional[str]:
        """Returns grafana url.

        Returns:
            str: grafana url
        """
        app_data = self.model.get_relation("replicas").data[self.app]  # type: ignore[union-attr]
        return app_data.get("grafana_url")


if __name__ == "__main__":
    main(MagmaNmsMagmalteCharm)
