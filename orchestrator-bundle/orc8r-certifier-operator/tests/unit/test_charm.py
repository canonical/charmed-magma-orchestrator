# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import base64
import io
import unittest
from typing import Tuple
from unittest.mock import Mock, call, patch

from certificates import (
    generate_ca,
    generate_certificate,
    generate_csr,
    generate_pfx_package,
    generate_private_key,
)
from cryptography.hazmat.primitives import serialization
from ops import testing
from ops.model import BlockedStatus, WaitingStatus
from pgconnstr import ConnectionString  # type: ignore[import]

from charm import MagmaOrc8rCertifierCharm

testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):

    TEST_DB_NAME = MagmaOrc8rCertifierCharm.DB_NAME
    TEST_DB_PORT = "1234"
    TEST_DB_CONNECTION_STRING = ConnectionString(
        "dbname=test_db_name "
        "fallback_application_name=whatever "
        "host=123.456.789.012 "
        "password=aaaBBBcccDDDeee "
        "port=1234 "
        "user=test_db_user"
    )

    @staticmethod
    def get_certificate_from_file(filename: str) -> str:
        with open(filename, "r") as file:
            certificate = file.read()
        return certificate

    @property
    def certificate(self) -> str:
        return self.get_certificate_from_file(filename="tests/unit/example.pem")

    @patch("charm.KubernetesServicePatch", lambda charm, ports, additional_labels: None)
    def setUp(self):
        self.model_name = "whatever"
        self.harness = testing.Harness(MagmaOrc8rCertifierCharm)
        self.harness.set_model_name(name=self.model_name)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.maxDiff = None

    @staticmethod
    def _fake_db_event(
        postgres_db_name: str,
        postgres_username: str,
        postgres_password: str,
        postgres_host: str,
        postgres_port: str,
    ):
        db_event = Mock()
        db_event.master = Mock()
        db_event.master.dbname = postgres_db_name
        db_event.master.user = postgres_username
        db_event.master.password = postgres_password
        db_event.master.host = postgres_host
        db_event.master.port = postgres_port
        return db_event

    @patch("charm.pgsql.PostgreSQLClient._mirror_appdata", new=Mock())
    def test_given_pod_is_leader_when_database_relation_joined_event_then_database_is_set_correctly(  # noqa: E501
        self,
    ):
        self.harness.set_leader(is_leader=True)
        postgres_db_name = self.TEST_DB_NAME
        postgres_host = "bread"
        postgres_password = "water"
        postgres_username = "yeast"
        postgres_port = self.TEST_DB_PORT
        with patch.object(MagmaOrc8rCertifierCharm, "DB_NAME", self.TEST_DB_NAME):
            db_event = self._fake_db_event(
                postgres_db_name,
                postgres_username,
                postgres_password,
                postgres_host,
                postgres_port,
            )
            self.harness.charm._on_database_relation_joined(db_event)
        self.assertEqual(db_event.database, self.TEST_DB_NAME)

    @patch("psycopg2.connect", new=Mock())
    @patch("ops.model.Container.exists")
    @patch("pgsql.opslib.pgsql.client.PostgreSQLClient._on_joined")
    def test_given_pebble_ready_when_get_plan_then_plan_is_filled_with_magma_orc8r_certifier_service_content(  # noqa: E501
        self, _, patch_file_exists
    ):
        patch_file_exists.return_value = True
        config_key_values = {"domain": "whatever domain"}
        self.harness.update_config(key_values=config_key_values)
        db_relation_id = self.harness.add_relation(relation_name="db", remote_app="postgresql-k8s")
        certificates_relation_id = self.harness.add_relation(
            relation_name="certificates", remote_app="vault-k8s"
        )
        self.harness.add_relation_unit(
            relation_id=db_relation_id, remote_unit_name="postgresql-k8s/0"
        )
        self.harness.add_relation_unit(
            relation_id=certificates_relation_id, remote_unit_name="vault-k8s/0"
        )
        key_values = {"master": self.TEST_DB_CONNECTION_STRING.__str__()}
        self.harness.update_relation_data(
            relation_id=db_relation_id, app_or_unit="postgresql-k8s", key_values=key_values
        )

        self.harness.container_pebble_ready(container_name="magma-orc8r-certifier")

        expected_plan = {
            "services": {
                "magma-orc8r-certifier": {
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
                        "DATABASE_SOURCE": f"dbname={self.TEST_DB_NAME} "
                        f"user={self.TEST_DB_CONNECTION_STRING.user} "
                        f"password={self.TEST_DB_CONNECTION_STRING.password} "
                        f"host={self.TEST_DB_CONNECTION_STRING.host} "
                        f"sslmode=disable",
                        "SQL_DRIVER": "postgres",
                        "SQL_DIALECT": "psql",
                        "SERVICE_HOSTNAME": "magma-orc8r-certifier",
                        "SERVICE_REGISTRY_MODE": "k8s",
                        "SERVICE_REGISTRY_NAMESPACE": self.model_name,
                    },
                }
            },
        }
        updated_plan = self.harness.get_container_pebble_plan("magma-orc8r-certifier").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.push")
    def test_given_pebble_ready_when_install_then_metricsd_config_file_is_created(
        self, patch_push, patch_exists
    ):
        patch_exists.return_value = False
        key_values = {"domain": "whatever.com"}
        self.harness.update_config(key_values=key_values)
        self.harness.container_pebble_ready("magma-orc8r-certifier")

        self.harness.charm.on.install.emit()

        patch_push.assert_any_call(
            path="/var/opt/magma/configs/orc8r/metricsd.yml",
            source='prometheusQueryAddress: "http://orc8r-prometheus:9090"\n'
            'alertmanagerApiURL: "http://orc8r-alertmanager:9093/api/v2"\n'
            '"profile": "prometheus"\n',
        )

    def test_given_pebble_not_ready_when_install_then_status_is_waiting(
        self,
    ):
        self.harness.charm.on.install.emit()

        assert self.harness.charm.unit.status == WaitingStatus("Waiting for container to be ready")

    @patch("ops.model.Container.push", new=Mock())
    @patch("charm.pgsql.PostgreSQLClient._mirror_appdata", new=Mock())
    def test_given_private_keys_are_not_stored_and_unit_is_leader_when_replicas_relation_created_then_private_keys_are_generated(  # noqa: E501
        self,
    ):
        self.harness.set_leader(is_leader=True)
        self.harness.container_pebble_ready("magma-orc8r-certifier")

        peer_relation_id = self.harness.add_relation("replicas", self.harness.charm.app.name)
        self.harness.add_relation_unit(peer_relation_id, self.harness.charm.app.name)

        relation_data = self.harness.get_relation_data(
            relation_id=peer_relation_id, app_or_unit=self.harness.charm.app.name
        )
        root_private_key = relation_data["root_private_key"]
        application_private_key = relation_data["application_private_key"]
        bootstrapper_private_key = relation_data["bootstrapper_private_key"]
        admin_operator_private_key = relation_data["admin_operator_private_key"]
        serialization.load_pem_private_key(root_private_key.encode(), password=None)
        serialization.load_pem_private_key(application_private_key.encode(), password=None)
        serialization.load_pem_private_key(bootstrapper_private_key.encode(), password=None)
        serialization.load_pem_private_key(admin_operator_private_key.encode(), password=None)

    @patch("ops.model.Container.push")
    @patch("charm.pgsql.PostgreSQLClient._mirror_appdata", new=Mock())
    def test_given_private_keys_are_not_stored_and_unit_is_leader_when_replicas_relation_created_then_private_keys_are_pushed_to_workload(  # noqa: E501
        self, patch_push
    ):
        self.harness.set_leader(is_leader=True)
        self.harness.container_pebble_ready("magma-orc8r-certifier")

        peer_relation_id = self.harness.add_relation("replicas", self.harness.charm.app.name)
        self.harness.add_relation_unit(peer_relation_id, self.harness.charm.app.name)

        call_list = patch_push.call_args_list
        assert len(call_list) == 4
        assert call_list[0].kwargs["path"] == "/var/opt/magma/certs/certifier.key"
        assert call_list[1].kwargs["path"] == "/var/opt/magma/certs/admin_operator.key.pem"
        assert call_list[2].kwargs["path"] == "/var/opt/magma/certs/bootstrapper.key"
        assert call_list[3].kwargs["path"] == "/var/opt/magma/certs/controller.key"
        serialization.load_pem_private_key(call_list[0].kwargs["source"].encode(), password=None)
        serialization.load_pem_private_key(call_list[1].kwargs["source"].encode(), password=None)
        serialization.load_pem_private_key(call_list[2].kwargs["source"].encode(), password=None)
        serialization.load_pem_private_key(call_list[3].kwargs["source"].encode(), password=None)

    def test_given_application_keys_are_not_stored_and_unit_is_not_leader_when_replicas_relation_created_then_status_is_waiting(  # noqa: E501
        self,
    ):
        self.harness.set_leader(is_leader=False)
        self.harness.container_pebble_ready("magma-orc8r-certifier")

        peer_relation_id = self.harness.add_relation("replicas", self.harness.charm.app.name)
        self.harness.add_relation_unit(peer_relation_id, self.harness.charm.app.name)

        assert self.harness.charm.unit.status == WaitingStatus(
            "Waiting for application private keys to be stored"
        )

    def test_given_root_private_keys_are_not_stored_and_unit_is_not_leader_when_replicas_relation_created_then_status_is_waiting(  # noqa: E501
        self,
    ):
        event = Mock()
        application_private_key = generate_private_key()
        bootstrapper_private_key = generate_private_key()
        admin_operator_private_key = generate_private_key()
        self.harness.set_leader(is_leader=False)
        self.harness.container_pebble_ready("magma-orc8r-certifier")
        peer_relation_id = self.harness.add_relation("replicas", self.harness.charm.app.name)
        self.harness.add_relation_unit(peer_relation_id, self.harness.charm.app.name)
        self.harness.update_relation_data(
            relation_id=peer_relation_id,
            app_or_unit=self.harness.charm.app.name,
            key_values={
                "application_private_key": application_private_key.decode(),
                "bootstrapper_private_key": bootstrapper_private_key.decode(),
                "admin_operator_private_key": admin_operator_private_key.decode(),
            },
        )

        self.harness.charm._on_replicas_relation_joined(event=event)

        assert self.harness.charm.unit.status == WaitingStatus(
            "Waiting for root private key to be stored"
        )

    @patch("ops.model.Container.push")
    @patch("charm.pgsql.PostgreSQLClient._mirror_appdata", new=Mock())
    def test_given_private_keys_are_stored_and_unit_is_not_leader_when_replicas_relation_created_then_private_keys_are_pushed_to_workload(  # noqa: E501
        self, patch_push
    ):
        event = Mock()
        root_private_key = generate_private_key()
        application_private_key = generate_private_key()
        bootstrapper_private_key = generate_private_key()
        admin_operator_private_key = generate_private_key()
        self.harness.set_leader(is_leader=False)
        self.harness.container_pebble_ready("magma-orc8r-certifier")
        peer_relation_id = self.harness.add_relation("replicas", self.harness.charm.app.name)
        self.harness.add_relation_unit(peer_relation_id, self.harness.charm.app.name)
        self.harness.update_relation_data(
            relation_id=peer_relation_id,
            app_or_unit=self.harness.charm.app.name,
            key_values={
                "root_private_key": root_private_key.decode(),
                "application_private_key": application_private_key.decode(),
                "bootstrapper_private_key": bootstrapper_private_key.decode(),
                "admin_operator_private_key": admin_operator_private_key.decode(),
            },
        )

        self.harness.charm._on_replicas_relation_joined(event=event)

        call_list = patch_push.call_args_list
        assert len(call_list) == 4
        assert call_list[0].kwargs["path"] == "/var/opt/magma/certs/certifier.key"
        assert call_list[1].kwargs["path"] == "/var/opt/magma/certs/admin_operator.key.pem"
        assert call_list[2].kwargs["path"] == "/var/opt/magma/certs/bootstrapper.key"
        assert call_list[3].kwargs["path"] == "/var/opt/magma/certs/controller.key"
        serialization.load_pem_private_key(call_list[0].kwargs["source"].encode(), password=None)
        serialization.load_pem_private_key(call_list[1].kwargs["source"].encode(), password=None)
        serialization.load_pem_private_key(call_list[2].kwargs["source"].encode(), password=None)
        serialization.load_pem_private_key(call_list[3].kwargs["source"].encode(), password=None)

    @patch("charm.pgsql.PostgreSQLClient._mirror_appdata", new=Mock())
    def test_given_config_not_valid_when_on_config_changed_then_status_is_blocked(
        self,
    ):
        self.harness.set_leader(is_leader=True)
        self.harness.container_pebble_ready("magma-orc8r-certifier")

        self.harness.update_config(key_values={})

        assert self.harness.charm.unit.status == BlockedStatus("Config 'domain' is not valid")

    @patch("charm.pgsql.PostgreSQLClient._mirror_appdata", new=Mock())
    def test_given_root_private_key_not_stored_when_on_config_changed_then_status_is_waiting(
        self,
    ):
        self.harness.set_leader(is_leader=True)
        self.harness.container_pebble_ready("magma-orc8r-certifier")

        self.harness.update_config(key_values={"domain": "whatever.com"})

        assert self.harness.charm.unit.status == WaitingStatus(
            "Waiting for root private key to be generated"
        )

    @patch("charm.pgsql.PostgreSQLClient._mirror_appdata", new=Mock())
    def test_given_cant_connect_to_container_when_on_config_changed_then_status_is_waiting(
        self,
    ):
        self.harness.set_leader(is_leader=True)

        self.harness.update_config(key_values={"domain": "whatever.com"})

        assert self.harness.charm.unit.status == WaitingStatus("Waiting for container to be ready")

    def create_peer_relation_with_certificates(  # noqa: C901
        self,
        domain_config: str,
        root_private_key: bool = False,
        admin_operator_private_key: bool = False,
        application_private_key: bool = False,
        application_certificate: bool = False,
        admin_operator_certificate: bool = False,
        root_csr: bool = False,
        root_certificate: bool = False,
        bootstrapper_private_key: bool = False,
    ) -> Tuple[int, dict]:
        """Creates a peer relation and adds certificates in its data.

        Args:
            domain_config: Domain config
            root_private_key: Set root private key
            admin_operator_private_key: Set admin operator private key
            application_private_key: Set application private key
            application_certificate: Set Application certificate
            admin_operator_certificate: Set Admin Operator certificate
            root_csr: Set Root CSR
            root_certificate: Set Root certificate
            bootstrapper_private_key: Set Bootstrapper private key

        Returns:
            int: Peer relation ID
            dict: Relation data
        """
        key_values = {}
        if root_private_key:
            key_values["root_private_key"] = generate_private_key().decode()
        if application_private_key:
            key_values["application_private_key"] = generate_private_key().decode()
        if admin_operator_private_key:
            key_values["admin_operator_private_key"] = generate_private_key().decode()
        if bootstrapper_private_key:
            key_values["bootstrapper_private_key"] = generate_private_key().decode()
        if root_csr:
            if not root_private_key:
                raise ValueError("root_private_key must be True if root_csr is True")
            key_values["root_csr"] = generate_csr(
                private_key=key_values["root_private_key"].encode(), subject=f"*.{domain_config}"
            ).decode()
        if root_certificate:
            if not root_csr:
                raise ValueError("root_csr must be True if root_certificate is True")
            if not root_private_key:
                raise ValueError("root_private_key must be True if root_certificate is True")
            ca_private_key = generate_private_key()
            ca_certificate = generate_ca(private_key=ca_private_key, subject="whatever")
            key_values["root_ca_certificate"] = ca_certificate.decode()
            key_values["root_certificate"] = generate_certificate(
                ca=ca_certificate,
                ca_key=ca_private_key,
                csr=key_values["root_csr"].encode(),
            ).decode()
        if application_certificate:
            application_ca_certificate = generate_ca(
                private_key=key_values["application_private_key"].encode(),
                subject=f"certifier.{domain_config}",
            )
            key_values["application_certificate"] = application_ca_certificate.decode()
        if admin_operator_certificate:
            if not application_certificate:
                raise ValueError(
                    "application_certificate must be True if admin_operator_certificate is True"
                )
            if not admin_operator_private_key:
                raise ValueError(
                    "admin_operator_private_key must be True if admin_operator_certificate is True"
                )
            pfx_password = "whatever"
            admin_operator_csr = generate_csr(
                private_key=key_values["admin_operator_private_key"].encode(),
                subject="admin_operator",
            )
            key_values["admin_operator_certificate"] = generate_certificate(
                csr=admin_operator_csr,
                ca=key_values["application_certificate"].encode(),
                ca_key=key_values["application_private_key"].encode(),
            ).decode()
            key_values["admin_operator_pfx_password"] = "whatever"
            pfx_package = generate_pfx_package(
                certificate=key_values["admin_operator_certificate"].encode(),
                private_key=key_values["admin_operator_private_key"].encode(),
                package_password=pfx_password,
            )
            key_values["admin_operator_pfx"] = str(base64.b64encode(pfx_package))

        peer_relation_id = self.harness.add_relation("replicas", self.harness.charm.app.name)
        self.harness.add_relation_unit(peer_relation_id, self.harness.charm.unit.name)

        self.harness.update_relation_data(
            relation_id=peer_relation_id,
            app_or_unit=self.harness.charm.app.name,
            key_values=key_values,
        )
        return peer_relation_id, key_values

    @patch("charm.pgsql.PostgreSQLClient._mirror_appdata", new=Mock())
    @patch("charm.generate_csr")
    @patch("charm.generate_pfx_package")
    @patch("charm.generate_certificate")
    @patch("charm.generate_ca")
    @patch(
        "charms.tls_certificates_interface.v1.tls_certificates.TLSCertificatesRequiresV1.request_certificate_renewal",  # noqa: E501,W505
        new=Mock(),
    )
    @patch("ops.model.Container.push")
    def test_given_stored_certificates_were_built_using_different_domain_when_on_config_changed_then_application_certificates_are_pushed_to_workload(  # noqa: E501
        self,
        patch_push,
        patch_generate_ca,
        patch_generate_certificate,
        patch_generate_pfx_package,
        patch_generate_csr,
    ):
        initial_domain_config = "old_whatever.com"
        new_domain_config = "new_whatever.com"
        new_ca_certificate = b"new ca certificate"
        new_application_certificate = b"new application certificate"
        new_pfx_package = b"new pfx package"
        new_csr = b"new csr"
        patch_generate_ca.return_value = new_ca_certificate
        patch_generate_certificate.return_value = new_application_certificate
        patch_generate_pfx_package.return_value = new_pfx_package
        patch_generate_csr.return_value = new_csr
        self.create_peer_relation_with_certificates(
            domain_config=initial_domain_config,
            root_csr=True,
            root_private_key=True,
            application_private_key=True,
            admin_operator_private_key=True,
            bootstrapper_private_key=True,
            admin_operator_certificate=True,
            application_certificate=True,
            root_certificate=True,
        )
        self.harness.set_leader(is_leader=True)
        self.harness.container_pebble_ready("magma-orc8r-certifier")

        self.harness.update_config(key_values={"domain": new_domain_config})

        patch_push.assert_any_call(
            path="/var/opt/magma/certs/certifier.pem",
            source=new_ca_certificate.decode(),
        )
        patch_push.assert_any_call(
            path="/var/opt/magma/certs/admin_operator.pem",
            source=new_application_certificate.decode(),
        )
        patch_push.assert_any_call(
            path="/var/opt/magma/certs/admin_operator.pfx",
            source=new_pfx_package,
        )

    @patch("charm.generate_csr")
    @patch(
        "charms.tls_certificates_interface.v1.tls_certificates.TLSCertificatesRequiresV1.request_certificate_creation",  # noqa: E501,W505
        new=Mock(),
    )
    @patch("charm.pgsql.PostgreSQLClient._mirror_appdata", new=Mock())
    def test_given_private_keys_are_stored_when_on_config_changed_then_root_csr_is_generated_and_stored_in_relation_data(  # noqa: E501
        self,
        patch_generate_csr,
    ):
        domain_config = "whatever"
        private_key = generate_private_key()
        generated_csr = generate_csr(private_key=private_key, subject="whatever subject")
        patch_generate_csr.return_value = generated_csr
        self.harness.set_leader(is_leader=True)
        peer_relation_id, key_values = self.create_peer_relation_with_certificates(
            domain_config=domain_config,
            root_csr=False,
            root_private_key=True,
            application_private_key=True,
            admin_operator_private_key=True,
            bootstrapper_private_key=True,
            application_certificate=True,
            admin_operator_certificate=True,
        )
        self.harness.container_pebble_ready("magma-orc8r-certifier")

        self.harness.update_config(key_values={"domain": domain_config})

        relation_data = self.harness.get_relation_data(
            relation_id=peer_relation_id, app_or_unit=self.harness.charm.app.name
        )
        assert relation_data["root_csr"] == generated_csr.decode()

    @patch("charm.pgsql.PostgreSQLClient._mirror_appdata", new=Mock())
    @patch("charm.generate_csr")
    def test_given_root_csr_is_stored_when_on_config_changed_then_root_csr_is_not_regenerated(
        self,
        patch_generate_csr,
    ):
        domain_config = "whatever"
        self.harness.set_leader(is_leader=True)
        self.create_peer_relation_with_certificates(domain_config=domain_config)
        self.harness.container_pebble_ready("magma-orc8r-certifier")

        self.harness.update_config(key_values={"domain": domain_config})

        patch_generate_csr.assert_not_called()

    @patch("charm.pgsql.PostgreSQLClient._mirror_appdata", new=Mock())
    @patch("ops.model.Container.push")
    def test_given_unit_is_not_leader_and_csr_is_not_stored_when_on_config_changed_then_status_is_waiting(  # noqa: E501
        self,
        _,
    ):
        domain_config = "whatever"
        self.harness.set_leader(is_leader=False)
        peer_relation_id = self.harness.add_relation("replicas", self.harness.charm.app.name)
        self.harness.add_relation_unit(peer_relation_id, self.harness.charm.unit.name)
        self.harness.update_relation_data(
            relation_id=peer_relation_id,
            app_or_unit=self.harness.charm.app.name,
            key_values={},
        )
        self.harness.container_pebble_ready("magma-orc8r-certifier")

        self.harness.update_config(key_values={"domain": domain_config})

        assert self.harness.charm.unit.status == WaitingStatus(
            "Waiting for leader to generate root csr"
        )

    @patch("charm.pgsql.PostgreSQLClient._mirror_appdata", new=Mock())
    @patch("ops.model.Container.push")
    def test_given_unit_is_not_leader_and_root_csr_is_stored_and_application_certificates_are_not_stored_when_on_config_changed_then_status_is_waiting(  # noqa: E501
        self,
        _,
    ):
        root_private_key = generate_private_key()
        domain_config = "whatever"
        self.harness.set_leader(is_leader=False)
        root_csr = generate_csr(private_key=root_private_key, subject=f"*.{domain_config}")
        peer_relation_id = self.harness.add_relation("replicas", self.harness.charm.app.name)
        self.harness.add_relation_unit(peer_relation_id, self.harness.charm.unit.name)
        self.harness.update_relation_data(
            relation_id=peer_relation_id,
            app_or_unit=self.harness.charm.app.name,
            key_values={
                "root_csr": root_csr.decode(),
            },
        )
        self.harness.container_pebble_ready("magma-orc8r-certifier")

        self.harness.update_config(key_values={"domain": domain_config})

        assert self.harness.charm.unit.status == WaitingStatus(
            "Waiting for leader to generate application certificates"
        )

    @patch("charm.MagmaOrc8rCertifierCharm._on_magma_orc8r_certifier_pebble_ready")
    @patch("charm.pgsql.PostgreSQLClient._mirror_appdata", new=Mock())
    @patch("ops.model.Container.push")
    def test_given_unit_is_not_leader_and_root_certificates_are_stored_when_on_config_changed_then_pebble_ready_handler_is_called(  # noqa: E501
        self, _, patch_pebble_ready
    ):
        domain_config = "whatever"
        self.harness.set_leader(is_leader=False)
        self.create_peer_relation_with_certificates(
            domain_config=domain_config,
            root_csr=True,
            application_private_key=True,
            root_private_key=True,
            admin_operator_private_key=True,
            bootstrapper_private_key=True,
            application_certificate=True,
            root_certificate=True,
            admin_operator_certificate=True,
        )
        self.harness.container_pebble_ready("magma-orc8r-certifier")

        self.harness.update_config(key_values={"domain": domain_config})

        patch_pebble_ready.assert_called()

    @patch("charm.pgsql.PostgreSQLClient._mirror_appdata", new=Mock())
    def test_given_default_domain_config_when_config_changed_then_status_is_blocked(self):
        key_values = {"domain": ""}
        self.harness.set_leader(is_leader=True)

        self.harness.update_config(key_values=key_values)

        assert self.harness.charm.unit.status == BlockedStatus("Config 'domain' is not valid")

    @patch("charm.pgsql.PostgreSQLClient._mirror_appdata", new=Mock())
    @patch(
        "charms.tls_certificates_interface.v1.tls_certificates.TLSCertificatesRequiresV1.request_certificate_creation"  # noqa: E501,W505
    )
    def test_given_root_csr_is_stored_when_certificates_relation_joined_then_certificates_are_requested(  # noqa: E501
        self, patch_request_certificates
    ):
        self.harness.set_leader(is_leader=True)
        certificates_relation_id = self.harness.add_relation(
            relation_name="certificates", remote_app="whatever app"
        )

        peer_relation_id, key_values = self.create_peer_relation_with_certificates(
            domain_config="whatever", root_csr=True, root_private_key=True
        )

        self.harness.add_relation_unit(
            relation_id=certificates_relation_id, remote_unit_name="whatever unit name"
        )

        patch_request_certificates.assert_called_with(
            certificate_signing_request=key_values["root_csr"].encode()
        )

    @patch("charm.pgsql.PostgreSQLClient._mirror_appdata", new=Mock())
    @patch(
        "charms.tls_certificates_interface.v1.tls_certificates.TLSCertificatesRequiresV1.request_certificate_creation"  # noqa: E501,W505
    )
    def test_given_unit_is_leader_and_root_csr_not_stored_when_certificates_relation_joined_then_certificates_arent_requested(  # noqa: E501
        self, patch_request_certificates
    ):
        self.harness.set_leader(is_leader=True)
        certificates_relation_id = self.harness.add_relation(
            relation_name="certificates", remote_app="whatever app"
        )
        self.create_peer_relation_with_certificates(domain_config="whatever")

        self.harness.add_relation_unit(
            relation_id=certificates_relation_id, remote_unit_name="whatever unit name"
        )

        self.assertEqual(0, patch_request_certificates.call_count)

    @patch("charm.pgsql.PostgreSQLClient._mirror_appdata", new=Mock())
    @patch(
        "charms.tls_certificates_interface.v1.tls_certificates.TLSCertificatesRequiresV1.request_certificate_creation"  # noqa: E501,W505
    )
    def test_given_unit_is_not_leader_and_root_csr_is_stored_when_certificates_relation_joined_then_certificates_arent_requested(  # noqa: E501
        self, patch_request_certificates
    ):
        self.harness.set_leader(is_leader=False)
        certificates_relation_id = self.harness.add_relation(
            relation_name="certificates", remote_app="whatever app"
        )
        self.create_peer_relation_with_certificates(
            domain_config="whatever",
            root_csr=True,
            root_private_key=True,
        )

        self.harness.add_relation_unit(
            relation_id=certificates_relation_id, remote_unit_name="whatever unit name"
        )

        patch_request_certificates.assert_not_called()

    @patch("charm.pgsql.PostgreSQLClient._mirror_appdata", new=Mock())
    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.push")
    def test_given_unit_is_leader_and_stored_root_csr_is_the_same_as_in_certificates_relation_when_certificate_available_then_certificate_and_key_are_pushed_to_workload(  # noqa: E501
        self, patch_push, patch_container_file_exists
    ):
        self.harness.set_leader(is_leader=True)
        patch_container_file_exists.return_value = False
        csr = "whatever csr"
        certificate = "whatever certificate"
        ca_certificate = "whatever ca certificate"
        event = Mock()
        event.certificate_signing_request = csr
        event.ca = ca_certificate
        event.certificate = certificate
        peer_relation_id = self.harness.add_relation("replicas", self.harness.charm.app.name)
        self.harness.add_relation_unit(peer_relation_id, self.harness.charm.app.name)
        self.harness.update_relation_data(
            relation_id=peer_relation_id,
            app_or_unit=self.harness.charm.app.name,
            key_values={"root_csr": csr},
        )
        self.harness.set_can_connect(container="magma-orc8r-certifier", val=True)

        self.harness.charm._on_certificate_available(event)

        calls = [
            call(path="/var/opt/magma/certs/rootCA.pem", source=ca_certificate),
            call(path="/var/opt/magma/certs/controller.crt", source=certificate),
        ]
        patch_push.assert_has_calls(calls)

    @patch("ops.model.Container.pull")
    @patch(
        "charms.magma_orc8r_certifier.v0.cert_admin_operator.CertAdminOperatorProvides.set_certificate"  # noqa: E501, W505
    )
    def test_given_certificate_is_stored_when_admin_operator_controller_certificate_request_then_certificate_is_set_in_admin_operator_lib(  # noqa: E501
        self, patch_set_private_key, patch_pull
    ):
        certificate_string = "whatever certificate"
        private_key_string = "whatever private key"
        event = Mock()
        relation_id = 3
        event.relation_id = relation_id
        certificate = io.StringIO(certificate_string)
        private_key = io.StringIO(private_key_string)
        patch_pull.side_effect = [certificate, private_key]
        container = self.harness.model.unit.get_container("magma-orc8r-certifier")
        self.harness.set_can_connect(container=container, val=True)

        self.harness.charm._on_admin_operator_certificate_request(event=event)

        patch_set_private_key.assert_called_with(
            private_key=private_key_string, certificate=certificate_string, relation_id=relation_id
        )

    @patch("ops.model.Container.pull")
    @patch(
        "charms.magma_orc8r_certifier.v0.cert_controller.CertControllerProvides.set_certificate"  # noqa: E501, W505
    )
    def test_given_certificate_is_stored_when_cert_controller_certificate_request_then_certificate_is_set_in_controller_lib(  # noqa: E501
        self, patch_set_private_key, patch_pull
    ):
        certificate_string = "whatever certificate"
        private_key_string = "whatever private key"
        event = Mock()
        relation_id = 3
        event.relation_id = relation_id
        certificate = io.StringIO(certificate_string)
        private_key = io.StringIO(private_key_string)
        patch_pull.side_effect = [certificate, private_key]
        container = self.harness.model.unit.get_container("magma-orc8r-certifier")
        self.harness.set_can_connect(container=container, val=True)

        self.harness.charm._on_controller_certificate_request(event=event)

        patch_set_private_key.assert_called_with(
            private_key=private_key_string, certificate=certificate_string, relation_id=relation_id
        )

    @patch("ops.model.Container.pull")
    @patch(
        "charms.magma_orc8r_certifier.v0.cert_bootstrapper.CertBootstrapperProvides.set_private_key"  # noqa: E501, W505
    )
    def test_given_private_key_is_stored_when_bootstrapper_private_key_request_then_private_key_is_set_in_bootstrapper_lib(  # noqa: E501
        self, patch_set_private_key, patch_pull
    ):
        private_key_string = "whatever private key"
        event = Mock()
        relation_id = 3
        event.relation_id = relation_id
        private_key = io.StringIO(private_key_string)
        patch_pull.return_value = private_key
        container = self.harness.model.unit.get_container("magma-orc8r-certifier")
        self.harness.set_can_connect(container=container, val=True)

        self.harness.charm._on_bootstrapper_private_key_request(event=event)

        patch_set_private_key.assert_called_with(
            private_key=private_key_string, relation_id=relation_id
        )
