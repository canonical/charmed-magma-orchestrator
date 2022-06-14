#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import base64
import logging

import ops.lib
import psycopg2  # type: ignore[import]
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from lightkube import Client
from lightkube.core.exceptions import ApiError
from lightkube.models.core_v1 import SecretVolumeSource, Volume, VolumeMount
from lightkube.models.meta_v1 import ObjectMeta
from lightkube.resources.apps_v1 import StatefulSet
from lightkube.resources.core_v1 import Secret
from lightkube.resources.core_v1 import Secret as SecretRes
from ops.charm import (
    CharmBase,
    ConfigChangedEvent,
    InstallEvent,
    PebbleReadyEvent,
    RelationJoinedEvent,
    RemoveEvent,
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
from ops.pebble import Layer, PathError
from pgconnstr import ConnectionString  # type: ignore[import]

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
        self._container_name = self._service_name = "magma-orc8r-certifier"
        self.provided_relation_name = list(self.meta.provides.keys())[0]
        provided_relation_name_with_underscores = self.provided_relation_name.replace("-", "_")
        self._container = self.unit.get_container(self._container_name)
        self._db = pgsql.PostgreSQLClient(self, "db")
        relation_joined_event = getattr(
            self.on, f"{provided_relation_name_with_underscores}_relation_joined"
        )
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(
            self.on.magma_orc8r_certifier_pebble_ready, self._on_magma_orc8r_certifier_pebble_ready
        )
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(
            relation_joined_event, self._on_magma_orc8r_certifier_relation_joined
        )
        self.framework.observe(
            self._db.on.database_relation_joined, self._on_database_relation_joined
        )
        self.framework.observe(self.on.remove, self._on_remove)
        self._nms_certs_secret_name = "nms-certs"
        self._orc8r_certs_secret_name = "orc8r-certs"
        self._nms_certs_data = {}
        self._orc8r_certs_data = {}
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[("grpc", 9180, 9086)],
            additional_labels={
                "app.kubernetes.io/part-of": "orc8r-app",
                "orc8r.io/analytics_collector": "true",
            },
        )

    def _on_install(self, event: InstallEvent):
        """Runs each time the charm is installed."""
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return
        self._write_metricsd_config_file()

    def _on_magma_orc8r_certifier_pebble_ready(self, event: PebbleReadyEvent):
        """Triggered when pebble is ready."""
        if not self._db_relation_created:
            self.unit.status = BlockedStatus("Waiting for database relation to be created")
            event.defer()
            return
        if not self._db_relation_established:
            self.unit.status = WaitingStatus("Waiting for database relation to be established")
            event.defer()
            return
        if not self._certs_are_mounted:
            self.unit.status = WaitingStatus("Waiting for certs to be mounted")
            event.defer()
            return
        self._configure_magma_orc8r_certifier(event)

    def _on_config_changed(self, event: ConfigChangedEvent):
        if not self._domain_config_is_valid:
            self.unit.status = BlockedStatus("Config 'domain' is not valid")
            logger.warning("Config 'domain' not valid")
            event.defer()
            return
        if not self._secrets_are_created:
            self._create_magma_orc8r_secrets()
        if not self._container.can_connect():
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()
            return
        if not self._certs_are_mounted:
            self._mount_certifier_certs()
        self._update_relations()

    def _on_magma_orc8r_certifier_relation_joined(self, event: RelationJoinedEvent):
        if not self.unit.is_leader():
            return
        self._update_relation_active_status(
            relation=event.relation, is_active=self._service_is_running
        )
        if not self._service_is_running:
            logger.warning(
                f"Service {self._service_name} not running! Please wait for the service to start."
            )
            event.defer()
            return

    def _on_database_relation_joined(self, event: RelationJoinedEvent):
        """
        Event handler for database relation change.
        - Sets the event.database field on the database joined event.
        - Required because setting the database name is only possible
          from inside the event handler per https://github.com/canonical/ops-lib-pgsql/issues/2
        - Sets our database parameters based on what was provided
          in the relation event.
        """
        if self.unit.is_leader():
            event.database = self.DB_NAME  # type: ignore[attr-defined]

    def _on_remove(self, event: RemoveEvent):
        self.unit.status = MaintenanceStatus("Removing Magma Orc8r secrets")
        self._delete_k8s_secret(secret_name=self._nms_certs_secret_name)
        self._delete_k8s_secret(secret_name=self._orc8r_certs_secret_name)

    def _write_metricsd_config_file(self):
        metricsd_config = (
            f'prometheusQueryAddress: "{self.PROMETHEUS_URL}"\n'
            f'alertmanagerApiURL: "{self.ALERTMANAGER_URL}/api/v2"\n'
            f'prometheusConfigServiceURL: "{self.PROMETHEUS_CONFIGURER_URL}/v1"\n'
            f'alertmanagerConfigServiceURL: "{self.ALERTMANAGER_CONFIGURER_URL}/v1"\n'
            '"profile": "prometheus"\n'
        )
        self._container.push(f"{self.BASE_CONFIG_PATH}/metricsd.yml", metricsd_config)

    def _configure_magma_orc8r_certifier(self, event: PebbleReadyEvent):
        """Adds layer to pebble config if the proposed config is different from the current one."""
        if self._container.can_connect():
            self.unit.status = MaintenanceStatus("Configuring pod")
            plan = self._container.get_plan()
            layer = self._pebble_layer
            if plan.services != layer.services:
                self._container.add_layer(self._container_name, layer, combine=True)
                self._container.restart(self._service_name)
                logger.info(f"Restarted container {self._service_name}")
                self._update_relations()
                self.unit.status = ActiveStatus()
        else:
            self.unit.status = WaitingStatus("Waiting for container to be ready")
            event.defer()

    def _update_relations(self):
        if not self.unit.is_leader():
            return
        relations = self.model.relations[self.provided_relation_name]
        for relation in relations:
            self._update_domain_name_in_relation_data(relation)
            self._update_relation_active_status(
                relation=relation, is_active=self._service_is_running
            )

    def _update_domain_name_in_relation_data(self, relation):
        """Updates the domain field inside the relation data bucket."""
        domain = self.model.config["domain"]
        relation.data[self.unit].update({"domain": domain})  # type: ignore[union-attr]

    def _create_magma_orc8r_secrets(self):
        self.unit.status = MaintenanceStatus("Creating Magma Orc8r secrets")
        self._get_certificates()
        self._create_secrets()

    def _get_certificates(self):
        if self.model.config["use-self-signed-ssl-certs"]:
            self._generate_self_signed_ssl_certs()
        else:
            self._load_certificates_from_configs()

    def _generate_self_signed_ssl_certs(self):
        logger.info("Creating self-signed certificates...")
        self._generate_admin_operator_cert()
        self._generate_controller_cert()
        self._generate_bootstrapper_cert()

    def _generate_admin_operator_cert(self):
        """
        Generates admin operator certificates.
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

        self._nms_certs_data["admin_operator.key.pem"] = self._encode_in_base64(
            admin_operator_key_pem
        )
        self._nms_certs_data["admin_operator.pem"] = self._encode_in_base64(admin_operator_pem)
        self._orc8r_certs_data["admin_operator.pem"] = self._encode_in_base64(admin_operator_pem)
        self._orc8r_certs_data["certifier.key"] = self._encode_in_base64(certifier_key)
        self._orc8r_certs_data["certifier.pem"] = self._encode_in_base64(certifier_pem)
        self._orc8r_certs_data["admin_operator.pfx"] = self._encode_in_base64(admin_operator_pfx)

    def _generate_controller_cert(self):
        """
        Generates controller certificates. List of certificates:
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

        self._nms_certs_data["controller.crt"] = self._encode_in_base64(controller_crt)
        self._nms_certs_data["controller.key"] = self._encode_in_base64(controller_key)
        self._orc8r_certs_data["controller.crt"] = self._encode_in_base64(controller_crt)
        self._orc8r_certs_data["controller.key"] = self._encode_in_base64(controller_key)
        self._orc8r_certs_data["rootCA.key"] = self._encode_in_base64(rootca_key)
        self._orc8r_certs_data["rootCA.pem"] = self._encode_in_base64(rootca_pem)

    def _generate_bootstrapper_cert(self):
        """
        Generates bootstrapper certificate.
        """
        bootstrapper_key = generate_private_key()
        self._orc8r_certs_data["bootstrapper.key"] = self._encode_in_base64(bootstrapper_key)

    def _load_certificates_from_configs(self):
        self._nms_certs_data = {
            "admin_operator.key.pem": self._encode_in_base64(
                self.model.config["admin-operator-key-pem"].encode()
            ),
            "admin_operator.pem": self._encode_in_base64(
                self.model.config["admin-operator-pem"].encode()
            ),
            "controller.crt": self._encode_in_base64(self.model.config["controller-crt"].encode()),
            "controller.key": self._encode_in_base64(self.model.config["controller-key"].encode()),
        }
        self._orc8r_certs_data = {
            "admin_operator.pem": self._encode_in_base64(
                self.model.config["admin-operator-pem"].encode()
            ),
            "controller.crt": self._encode_in_base64(self.model.config["controller-crt"].encode()),
            "controller.key": self._encode_in_base64(self.model.config["controller-key"].encode()),
            "bootstrapper.key": self._encode_in_base64(
                self.model.config["bootstrapper-key"].encode()
            ),
            "certifier.key": self._encode_in_base64(self.model.config["certifier-key"].encode()),
            "certifier.pem": self._encode_in_base64(self.model.config["certifier-pem"].encode()),
            "rootCA.key": self._encode_in_base64(self.model.config["rootCA-key"].encode()),
            "rootCA.pem": self._encode_in_base64(self.model.config["rootCA-pem"].encode()),
        }

    def _create_secrets(self):
        logger.info("Creating k8s secrets")
        self._create_k8s_secret(
            secret_name=self._nms_certs_secret_name, secret_data=self._nms_certs_data
        )
        self._create_k8s_secret(
            secret_name=self._orc8r_certs_secret_name, secret_data=self._orc8r_certs_data
        )

    def _create_k8s_secret(self, secret_name: str, secret_data: dict):
        logger.info(f"Creating k8s secret for '{secret_name}'")
        secret = Secret(
            apiVersion="v1",
            data=secret_data,
            metadata=ObjectMeta(
                labels={"app.kubernetes.io/name": self.app.name},
                name=secret_name,
                namespace=self._namespace,
            ),
            kind="Secret",
            type="Opaque",
        )
        try:
            client = Client()
            client.create(secret)
        except ApiError as e:
            logger.info("Failed to create Secret: %s.", str(secret.to_dict()))
            raise e
        return True

    def _mount_certifier_certs(self):
        """Patch the StatefulSet to include certs secret mount."""
        self.unit.status = MaintenanceStatus("Mounting additional volumes")
        logger.info("Mounting volumes for certificates")
        client = Client()
        stateful_set = client.get(StatefulSet, name=self.app.name, namespace=self._namespace)
        stateful_set.spec.template.spec.volumes.extend(self._magma_orc8r_certifier_volumes)  # type: ignore[attr-defined]  # noqa: E501
        stateful_set.spec.template.spec.containers[1].volumeMounts.extend(  # type: ignore[attr-defined]  # noqa: E501
            self._magma_orc8r_certifier_volume_mounts
        )
        client.patch(StatefulSet, name=self.app.name, obj=stateful_set, namespace=self._namespace)
        logger.info("Additional volumes for certificates are mounted")

    def _delete_k8s_secret(self, secret_name: str) -> None:
        """Delete Kubernetes secrets created by the create_secrets method."""
        client = Client()
        client.delete(SecretRes, name=secret_name, namespace=self._namespace)
        logger.info("Deleted Kubernetes secrets!")

    def _update_relation_active_status(self, relation: Relation, is_active: bool):
        relation.data[self.unit].update(
            {
                "active": str(is_active),
            }
        )

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
    def _secrets_are_created(self) -> bool:
        client = Client()
        try:
            client.get(res=Secret, name="orc8r-certs")
            client.get(res=Secret, name="nms-certs")
            logger.info("Secrets are already created")
            return True
        except ApiError:
            logger.info("Kubernetes secrets are not already created")
            return False

    @property
    def _certs_are_mounted(self) -> bool:
        try:
            self._container.pull(f"{self.BASE_CERTS_PATH}/certifier.pem")
            logger.info("Certificates are already mounted to workload")
            return True
        except PathError:
            logger.info("Certificates are not already mounted to workload")
            return False

    @property
    def _magma_orc8r_certifier_volumes(self) -> list:
        """Returns a list of volumes required by the magma-orc8r-certifier container."""
        return [
            Volume(
                name="certs",
                secret=SecretVolumeSource(secretName=self._orc8r_certs_secret_name),
            ),
        ]

    @property
    def _magma_orc8r_certifier_volume_mounts(self) -> list:
        """Returns a list of volume mounts required by the magma-orc8r-certifier container."""
        return [
            VolumeMount(
                mountPath=self.BASE_CERTS_PATH,
                name="certs",
                readOnly=True,
            ),
        ]

    @staticmethod
    def _encode_in_base64(byte_string: bytes):
        """Encodes given byte string in Base64"""
        return base64.b64encode(byte_string).decode("utf-8")

    @property
    def _service_is_running(self) -> bool:
        if self._container.can_connect():
            try:
                self._container.get_service(self._service_name)
                return True
            except ModelError:
                pass
        return False

    @property
    def _namespace(self) -> str:
        return self.model.name


if __name__ == "__main__":
    main(MagmaOrc8rCertifierCharm)
