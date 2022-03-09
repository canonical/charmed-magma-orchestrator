#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import base64
import logging

import ops.lib
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from lightkube import Client, codecs
from lightkube.core.exceptions import ApiError
from lightkube.models.core_v1 import SecretVolumeSource, Volume, VolumeMount
from lightkube.resources.apps_v1 import StatefulSet
from lightkube.resources.core_v1 import Secret as SecretRes
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer
from pgconnstr import ConnectionString  # type: ignore[import]

from client_relations import ClientRelations
from self_signed_certs_creator import (
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

    def __init__(self, *args):
        """An instance of this object everytime an event occurs."""
        super().__init__(*args)
        self._container_name = self._service_name = "magma-orc8r-certifier"
        self._container = self.unit.get_container(self._container_name)
        self.client_relations = ClientRelations(self, "client_relations")
        self._db = pgsql.PostgreSQLClient(self, "db")
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(
            self.on.magma_orc8r_certifier_pebble_ready, self._on_magma_orc8r_certifier_pebble_ready
        )
        self.framework.observe(
            self._db.on.database_relation_joined, self._on_database_relation_joined
        )
        self.framework.observe(self.on.remove, self._on_remove)
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[("grpc", 9180, 9086)],
            additional_labels={
                "app.kubernetes.io/part-of": "orc8r-app",
                "orc8r.io/analytics_collector": "true",
            },
        )

    def _on_install(self, event):
        """Runs each time the charm is installed."""
        if self._container.can_connect():
            self._create_magma_orc8r_secrets()
            self._mount_certifier_certs()
        else:
            self.unit.status = WaitingStatus("Waiting for container to be ready...")
            event.defer()
            return

    def _on_magma_orc8r_certifier_pebble_ready(self, event):
        """Triggered when pebble is ready."""
        if not self._db_relation_created:
            self.unit.status = BlockedStatus("Waiting for database relation to be created")
            event.defer()
            return
        if not self._db_relation_established:
            self.unit.status = WaitingStatus("Waiting for database relation to be established...")
            event.defer()
            return
        self._configure_magma_orc8r_certifier(event)

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

    @property
    def _db_relation_created(self) -> bool:
        """Checks whether required relations are ready."""
        if not self.model.get_relation("db"):
            return False
        return True

    @property
    def _db_relation_established(self) -> bool:
        """Validates that database relation is established (that there is a relation and that
        credentials have been passed)."""
        if not self._get_db_connection_string:
            return False
        return True

    def _create_magma_orc8r_secrets(self):
        self.unit.status = MaintenanceStatus("Creating Magma Orc8r secrets...")
        if self.model.config["use-self-signed-ssl-certs"]:
            self._generate_self_signed_ssl_certs()
        self._create_secrets()

    def _mount_certifier_certs(self) -> None:
        """Patch the StatefulSet to include certs secret mount."""
        self.unit.status = MaintenanceStatus(
            "Mounting additional volumes required by the magma-orc8r-certifier container..."
        )
        client = Client()
        stateful_set = client.get(StatefulSet, name=self.app.name, namespace=self._namespace)
        stateful_set.spec.template.spec.volumes.extend(self._magma_orc8r_certifier_volumes)  # type: ignore[attr-defined]  # noqa: E501
        stateful_set.spec.template.spec.containers[1].volumeMounts.extend(  # type: ignore[attr-defined]  # noqa: E501
            self._magma_orc8r_certifier_volume_mounts
        )
        client.patch(StatefulSet, name=self.app.name, obj=stateful_set, namespace=self._namespace)
        logger.info("Additional K8s resources for magma-orc8r-certifier container applied!")

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

    def _on_remove(self, event):
        self.unit.status = MaintenanceStatus("Removing Magma Orc8r secrets...")
        self._delete_secrets()

    def _create_secrets(self) -> bool:
        """Creates Secrets which are provided by the magma-orc8r-certifier."""
        client = Client()
        for secret_name, secret_data in self._magma_orc8r_certifier_secrets.items():
            context = {
                "app_name": self.app.name,
                "namespace": self._namespace,
                "secret_name": secret_name,
                "secret_data": secret_data,
            }
            with open("src/templates/secret.yaml.j2") as secret_manifest:
                secret = codecs.load_all_yaml(secret_manifest, context=context)[0]
                try:
                    client.create(secret)
                except ApiError as e:
                    logger.info("Failed to create Secret: %s.", str(secret.to_dict()))
                    raise e
        return True

    def _delete_secrets(self) -> None:
        """Delete Kubernetes secrets created by the create_secrets method"""
        client = Client()
        for secret in self._magma_orc8r_certifier_secrets:
            client.delete(SecretRes, name=secret, namespace=self._namespace)
        logger.info("Deleted Kubernetes secrets!")

    def _generate_self_signed_ssl_certs(self):
        logger.info("Creating self-signed certificates...")
        self._generate_admin_operator_cert()
        self._generate_controller_cert()
        self._generate_bootstrapper_cert()

    def _generate_admin_operator_cert(self):
        """
        Generates admin operator certificates and pushes them to the "/tmp/certs" directory.
        List of certificates:
            1. Generates Certifier certificate to sign AdminOperator certificate
            2. Generate AdminOperator private key to create CSR
            3. Generate AdminOperator CSR (Certificate Signing Request)
            4. Generate AdminOperator certificate
        """

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

        self._container.push("/tmp/certs/certifier.key", certifier_key)
        self._container.push("/tmp/certs/certifier.pem", certifier_pem)
        self._container.push("/tmp/certs/admin_operator.key.pem", admin_operator_key_pem)
        self._container.push("/tmp/certs/admin_operator.csr", admin_operator_csr)
        self._container.push("/tmp/certs/admin_operator.pem", admin_operator_pem)
        self._container.push("/tmp/certs/admin_operator.pfx", admin_operator_pfx)

    def _generate_bootstrapper_cert(self):
        """
        Generates bootstrapper certificate and pushes it to the "/tmp/certs" directory.
        """
        bootstrapper_key = generate_private_key()
        self._container.push("/tmp/certs/bootstrapper.key", bootstrapper_key)

    def _generate_controller_cert(self):
        """
        Generates controller certificates and pushes them to the "/tmp/certs" directory. List of
        certificates:
            1. Generate rootCA certificate to sign AdminOperator certificate
            2. Generate Controller private key to create CSR
            3. Generate Controller CSR (Certificate Signing Request)
            4. Generate Controller certificate
        """

        rootca_key = generate_private_key()
        rootca_pem = generate_ca(
            private_key=rootca_key,
            subject=f"rootca.{self.model.config['domain']}",
        )
        controller_key = generate_private_key()
        controller_csr = generate_csr(
            private_key=controller_key, subject=f"*.{self.model.config['domain']}"
        )
        controller_crt = generate_certificate(
            csr=controller_csr,
            ca=rootca_pem,
            ca_key=rootca_key,
        )

        self._container.push("/tmp/certs/rootCA.key", rootca_key)
        self._container.push("/tmp/certs/rootCA.pem", rootca_pem)
        self._container.push("/tmp/certs/controller.key", controller_key)
        self._container.push("/tmp/certs/controller.csr", controller_csr)
        self._container.push("/tmp/certs/controller.crt", controller_crt)

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
                        "-cac=/var/opt/magma/certs/certifier.pem "
                        "-cak=/var/opt/magma/certs/certifier.key "
                        "-vpnc=/var/opt/magma/certs/vpn_ca.crt "
                        "-vpnk=/var/opt/magma/certs/vpn_ca.key "
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
    def _magma_orc8r_certifier_secrets(self) -> dict:
        """Return a list of secrets to be provided by the magma-orc8r-certifier."""
        if self.model.config["use-self-signed-ssl-certs"]:
            nms_certs_data = {
                "controller.crt": self._encode_in_base64(
                    open("/tmp/certs/controller.crt", "rb").read()
                ),
                "controller.key": self._encode_in_base64(
                    open("/tmp/certs/controller.key", "rb").read()
                ),
                "admin_operator.key.pem": self._encode_in_base64(
                    open("/tmp/certs/admin_operator.key.pem", "rb").read()
                ),
                "admin_operator.pem": self._encode_in_base64(
                    open("/tmp/certs/admin_operator.pem", "rb").read()
                ),
            }
            orc8r_certs_data = {
                "admin_operator.pem": self._encode_in_base64(
                    open("/tmp/certs/admin_operator.pem", "rb").read()
                ),
                "controller.crt": self._encode_in_base64(
                    open("/tmp/certs/controller.crt", "rb").read()
                ),
                "controller.key": self._encode_in_base64(
                    open("/tmp/certs/controller.key", "rb").read()
                ),
                "bootstrapper.key": self._encode_in_base64(
                    open("/tmp/certs/bootstrapper.key", "rb").read()
                ),
                "certifier.key": self._encode_in_base64(
                    open("/tmp/certs/certifier.key", "rb").read()
                ),
                "certifier.pem": self._encode_in_base64(
                    open("/tmp/certs/certifier.pem", "rb").read()
                ),
                "rootCA.key": self._encode_in_base64(open("/tmp/certs/rootCA.key", "rb").read()),
                "rootCA.pem": self._encode_in_base64(open("/tmp/certs/rootCA.pem", "rb").read()),
            }
        else:
            nms_certs_data = {
                "admin_operator.key.pem": self._encode_in_base64(
                    self.model.config["admin-operator-key-pem"].encode()
                ),
                "admin_operator.pem": self._encode_in_base64(
                    self.model.config["admin-operator-pem"].encode()
                ),
                "controller.crt": self._encode_in_base64(
                    self.model.config["controller-crt"].encode()
                ),
                "controller.key": self._encode_in_base64(
                    self.model.config["controller-key"].encode()
                ),
            }
            orc8r_certs_data = {
                "admin_operator.pem": self._encode_in_base64(
                    self.model.config["admin-operator-pem"].encode()
                ),
                "controller.crt": self._encode_in_base64(
                    self.model.config["controller-crt"].encode()
                ),
                "controller.key": self._encode_in_base64(
                    self.model.config["controller-key"].encode()
                ),
                "bootstrapper.key": self._encode_in_base64(
                    self.model.config["bootstrapper-key"].encode()
                ),
                "certifier.key": self._encode_in_base64(
                    self.model.config["certifier-key"].encode()
                ),
                "certifier.pem": self._encode_in_base64(
                    self.model.config["certifier-pem"].encode()
                ),
                "rootCA.key": self._encode_in_base64(self.model.config["rootCA-key"].encode()),
                "rootCA.pem": self._encode_in_base64(self.model.config["rootCA-pem"].encode()),
            }
        return {"nms-certs": nms_certs_data, "orc8r-certs": orc8r_certs_data}

    @property
    def _magma_orc8r_certifier_volumes(self) -> list:
        """Returns a list of volumes required by the magma-orc8r-certifier container."""
        return [
            Volume(
                name="certs",
                secret=SecretVolumeSource(secretName="orc8r-certs"),
            ),
        ]

    @property
    def _magma_orc8r_certifier_volume_mounts(self) -> list:
        """Returns a list of volume mounts required by the magma-orc8r-certifier container."""
        return [
            VolumeMount(
                mountPath="/var/opt/magma/certs",
                name="certs",
                readOnly=True,
            ),
        ]

    @property
    def _get_db_connection_string(self):
        """Returns DB connection string provided by the DB relation."""
        try:
            db_relation = self.model.get_relation("db")
            return ConnectionString(db_relation.data[db_relation.app]["master"])
        except (AttributeError, KeyError):
            return None

    @staticmethod
    def _encode_in_base64(byte_string: bytes):
        """Encodes given byte string in Base64"""
        return base64.b64encode(byte_string).decode("utf-8")

    @property
    def _namespace(self) -> str:
        return self.model.name


if __name__ == "__main__":
    main(MagmaOrc8rCertifierCharm)
