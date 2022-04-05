#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import secrets
import string
import time
from typing import List

import ops.lib
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from lightkube import Client
from lightkube.models.core_v1 import SecretVolumeSource, Volume, VolumeMount
from lightkube.resources.apps_v1 import StatefulSet
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
    _stored = StoredState()

    def __init__(self, *args):
        """Creates a new instance of this object for each event."""
        super().__init__(*args)
        self._container_name = self._service_name = "magma-nms-magmalte"
        self._container = self.unit.get_container(self._container_name)
        self._stored.set_default(admin_username="", admin_password="")
        self._db = pgsql.PostgreSQLClient(self, "db")
        self.framework.observe(
            self.on.magma_nms_magmalte_pebble_ready, self._on_magma_nms_magmalte_pebble_ready
        )
        self.framework.observe(
            self._db.on.database_relation_joined, self._on_database_relation_joined
        )
        self.framework.observe(
            self.on.certifier_relation_changed, self._on_certifier_relation_changed
        )
        self.framework.observe(
            self.on.get_admin_credentials_action, self._on_get_admin_credentials
        )
        self.framework.observe(
            self.on.create_nms_admin_user_action, self._create_nms_admin_user_action
        )
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[("magmalte", 8081, 8081)],
            service_name="magmalte",
            additional_labels={
                "app.kubernetes.io/part-of": "magma",
                "app.kubernetes.io/component": "magmalte",
            },
        )

    def _on_magma_nms_magmalte_pebble_ready(self, event):
        if not self._relations_ready:
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

    def _on_certifier_relation_changed(self, event):
        """Mounts certificates required by the magma-nms-magmalte."""
        if not self._nms_certs_mounted:
            self.unit.status = MaintenanceStatus("Mounting NMS certificates...")
            self._mount_certifier_certs()

    def _configure_pebble(self, event):
        """Adds layer to pebble config if the proposed config is different from the current one."""
        if self._container.can_connect():
            plan = self._container.get_plan()
            layer = self._pebble_layer
            if plan.services != layer.services:
                self.unit.status = MaintenanceStatus(
                    f"Configuring pebble layer for {self._service_name}..."
                )
                self._container.add_layer(self._container_name, layer, combine=True)
                self._container.restart(self._service_name)
                logger.info(f"Restarted container {self._service_name}")
                self.unit.status = ActiveStatus()
        else:
            self.unit.status = WaitingStatus("Waiting for container to be ready...")
            event.defer()

    def _mount_certifier_certs(self) -> None:
        """Patch the StatefulSet to include NMS certs secret mount."""
        self.unit.status = MaintenanceStatus(
            "Mounting additional volumes required by the magma-nms-magmalte container..."
        )
        client = Client()
        stateful_set = client.get(StatefulSet, name=self.app.name, namespace=self._namespace)
        stateful_set.spec.template.spec.volumes.extend(self._magma_nms_magmalte_volumes)  # type: ignore[attr-defined]  # noqa: E501
        stateful_set.spec.template.spec.containers[1].volumeMounts.extend(  # type: ignore[attr-defined]  # noqa: E501
            self._magma_nms_magmalte_volume_mounts
        )
        client.patch(StatefulSet, name=self.app.name, obj=stateful_set, namespace=self._namespace)
        logger.info("Additional K8s resources for magma-nms-magmalte container applied!")

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
        Creates Admin user for the master organization in NMS
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
    def _magma_nms_magmalte_volumes(self) -> List[Volume]:
        """Returns the additional volumes required by the magma-nms-magmalte container."""
        return [
            Volume(
                name="orc8r-secrets-certs",
                secret=SecretVolumeSource(secretName="nms-certs"),
            ),
        ]

    @property
    def _magma_nms_magmalte_volume_mounts(self) -> List[VolumeMount]:
        """Returns the additional volume mounts for the magma-nms-magmalte container."""
        return [
            VolumeMount(
                mountPath="/run/secrets/admin_operator.pem",
                name="orc8r-secrets-certs",
                subPath="admin_operator.pem",
            ),
            VolumeMount(
                mountPath="/run/secrets/admin_operator.key.pem",
                name="orc8r-secrets-certs",
                subPath="admin_operator.key.pem",
            ),
        ]

    @property
    def _relations_ready(self) -> bool:
        """Checks whether required relations are ready."""
        required_relations = ["certifier", "db"]
        missing_relations = [
            relation for relation in required_relations if not self.model.get_relation(relation)
        ]
        if missing_relations:
            self.unit.status = BlockedStatus(
                f"Waiting for relation(s) to be created: {', '.join(missing_relations)}"
            )
            return False
        if not self._domain_name:
            self.unit.status = WaitingStatus("Waiting for certifier relation to be ready...")
            return False
        if not self._get_db_connection_string:
            self.unit.status = WaitingStatus("Waiting for database relation to be established...")
            return False
        return True

    @property
    def _nms_certs_mounted(self) -> bool:
        """Check to see if the NMS certs have already been mounted."""
        client = Client()
        statefulset = client.get(StatefulSet, name=self.app.name, namespace=self._namespace)
        return all(
            volume_mount in statefulset.spec.template.spec.containers[1].volumeMounts  # type: ignore[attr-defined]  # noqa: E501
            for volume_mount in self._magma_nms_magmalte_volume_mounts
        )

    @property
    def _domain_name(self):
        """Returns domain name provided by the orc8r-certifier relation."""
        try:
            certifier_relation = self.model.get_relation("certifier")
            units = certifier_relation.units
            return certifier_relation.data[next(iter(units))]["domain"]
        except (KeyError, StopIteration):
            return None

    @property
    def _get_db_connection_string(self):
        """Returns DB connection string provided by the DB relation."""
        try:
            db_relation = self.model.get_relation("db")
            return ConnectionString(db_relation.data[db_relation.app]["master"])
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
            self._stored.admin_username = f"admin@{self._domain_name}"
        return self._stored.admin_username

    @staticmethod
    def _generate_password() -> str:
        """Generates a random 12 character password."""
        chars = string.ascii_letters + string.digits
        return "".join(secrets.choice(chars) for _ in range(12))


if __name__ == "__main__":
    main(MagmaNmsMagmalteCharm)
