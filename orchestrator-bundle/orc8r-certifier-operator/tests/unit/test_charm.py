# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import base64
import io
import unittest
from unittest.mock import Mock, call, patch

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

    @patch("charm.KubernetesServicePatch", lambda charm, ports, additional_labels: None)
    @patch("pgsql.opslib.pgsql.client.PostgreSQLClient._mirror_appdata", new=Mock())
    def setUp(self):
        self.model_name = "whatever"
        self.harness = testing.Harness(MagmaOrc8rCertifierCharm)
        self.harness.set_model_name(name=self.model_name)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.maxDiff = None
        self.peer_relation_id = self.harness.add_relation("replicas", self.harness.charm.app.name)
        self.harness.add_relation_unit(self.peer_relation_id, self.harness.charm.unit.name)
        self.harness.set_leader(True)

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

    @patch("ops.model.Unit.is_leader")
    def test_given_pod_is_leader_when_database_relation_joined_event_then_database_is_set_correctly(  # noqa: E501
        self, is_leader
    ):
        is_leader.return_value = True
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

    @patch("charm.generate_csr", new=Mock())
    @patch("charm.generate_pfx_package")
    @patch("charm.generate_certificate")
    @patch("charm.generate_ca")
    @patch("charm.generate_private_key")
    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.push")
    def test_given_pebble_ready_when_install_then_admin_application_certificates_are_created(
        self,
        patch_push,
        patch_exists,
        patch_generate_private_key,
        patch_generate_ca,
        patch_generate_certificate,
        patch_generate_pfx_package,
    ):
        private_key_1 = b"whatever private key 1"
        private_key_2 = b"whatever private key 2"
        private_key_3 = b"whatever private key 3"
        certificate = b"whatever certificate"
        ca_certificate = b"whatever ca certificate"
        pfx_package = b"whatever pfx package content"

        patch_generate_private_key.side_effect = [private_key_1, private_key_2, private_key_3]
        patch_generate_ca.return_value = ca_certificate
        patch_generate_certificate.return_value = certificate
        patch_generate_pfx_package.return_value = pfx_package
        patch_exists.return_value = False
        key_values = {"domain": "whatever.com"}
        self.harness.update_config(key_values=key_values)
        self.harness.container_pebble_ready("magma-orc8r-certifier")

        self.harness.charm.on.install.emit()

        patch_push.assert_any_call(
            path="/var/opt/magma/certs/certifier.pem",
            source=ca_certificate,
        )
        patch_push.assert_any_call(
            path="/var/opt/magma/certs/certifier.key",
            source=private_key_1,
        )
        patch_push.assert_any_call(
            path="/var/opt/magma/certs/admin_operator.pem",
            source=certificate,
        )
        patch_push.assert_any_call(
            path="/var/opt/magma/certs/admin_operator.key.pem",
            source=private_key_2,
        )
        patch_push.assert_any_call(
            path="/var/opt/magma/certs/admin_operator.pfx",
            source=pfx_package,
        )
        patch_push.assert_any_call(
            path="/var/opt/magma/certs/bootstrapper.key",
            source=private_key_3,
        )

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.push")
    def test_given_pebble_ready_when_install_and_unit_is_not_leader_then_status_is_waiting(
        self,
        patch_push,
        patch_exists,
    ):
        patch_exists.return_value = False
        key_values = {"domain": "whatever.com"}
        self.harness.update_config(key_values=key_values)
        self.harness.container_pebble_ready("magma-orc8r-certifier")
        self.harness.set_leader(False)

        self.harness.charm.on.install.emit()

        assert self.harness.charm.unit.status == WaitingStatus(
            "Waiting for leader to generate certificates"
        )
        patch_push.assert_not_called()

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.push")
    def test_given_pebble_ready_when_install_and_unit_is_not_leader_and_certs_are_generated_then_admin_application_certificates_are_pushed(  # noqa: E501
        self,
        patch_push,
        patch_exists,
    ):
        private_key_1 = b"whatever private key 1"
        private_key_2 = b"whatever private key 2"
        private_key_3 = b"whatever private key 3"
        certificate = b"whatever certificate"
        ca_certificate = b"whatever ca certificate"
        pfx_package = b"whatever pfx package content"

        patch_exists.return_value = False
        key_values = {"domain": "whatever.com"}
        self.harness.update_config(key_values=key_values)
        self.harness.container_pebble_ready("magma-orc8r-certifier")
        self.harness.set_leader(False)
        self.harness.update_relation_data(
            relation_id=self.peer_relation_id,
            app_or_unit=self.harness.charm.app.name,
            key_values={
                "certifier_pem": ca_certificate.decode(),
                "certifier_key": private_key_1.decode(),
                "admin_operator_pem": certificate.decode(),
                "admin_operator_key_pem": private_key_2.decode(),
                "admin_operator_pfx": base64.b64encode(pfx_package).decode(),
                "bootstrapper_key": private_key_3.decode(),
                "admin_operator_password": "password",
            },
        )

        self.harness.charm.on.install.emit()

        patch_push.assert_any_call(
            path="/var/opt/magma/certs/certifier.pem",
            source=ca_certificate,
        )
        patch_push.assert_any_call(
            path="/var/opt/magma/certs/certifier.key",
            source=private_key_1,
        )
        patch_push.assert_any_call(
            path="/var/opt/magma/certs/admin_operator.pem",
            source=certificate,
        )
        patch_push.assert_any_call(
            path="/var/opt/magma/certs/admin_operator.key.pem",
            source=private_key_2,
        )
        patch_push.assert_any_call(
            path="/var/opt/magma/certs/admin_operator.pfx",
            source=pfx_package,
        )
        patch_push.assert_any_call(
            path="/var/opt/magma/certs/bootstrapper.key",
            source=private_key_3,
        )

    def test_given_default_domain_config_when_config_changed_then_status_is_blocked(self):
        key_values = {"domain": ""}
        self.harness.container_pebble_ready("magma-orc8r-certifier")

        self.harness.update_config(key_values=key_values)

        assert self.harness.charm.unit.status == BlockedStatus("Config 'domain' is not valid")

    @patch(
        "charms.tls_certificates_interface.v0.tls_certificates.TLSCertificatesRequires.request_certificate"  # noqa: E501,W505
    )
    def test_given_correct_domain_when_certificates_relation_joined_then_certificates_are_requested(  # noqa: E501
        self, patch_request_certificates
    ):
        common_name = "whatever.domain"
        key_values = {"domain": common_name}
        relation_id = self.harness.add_relation(
            relation_name="certificates", remote_app="whatever app"
        )
        self.harness.update_config(key_values=key_values)

        self.harness.add_relation_unit(
            relation_id=relation_id, remote_unit_name="whatever unit name"
        )

        calls = [call(cert_type="server", common_name=f"*.{common_name}")]
        patch_request_certificates.assert_has_calls(calls)

    @patch(
        "charms.tls_certificates_interface.v0.tls_certificates.TLSCertificatesRequires.request_certificate"  # noqa: E501,W505
    )
    def test_given_domain_not_set_when_certificates_relation_joined_then_certificates_arent_set(  # noqa: E501
        self, patch_request_certificates
    ):
        key_values = {"domain": ""}
        relation_id = self.harness.add_relation(
            relation_name="certificates", remote_app="whatever app"
        )
        self.harness.update_config(key_values=key_values)

        self.harness.add_relation_unit(
            relation_id=relation_id, remote_unit_name="whatever unit name"
        )

        self.assertEqual(0, patch_request_certificates.call_count)

    @patch("ops.model.Container.exists")
    @patch("ops.model.Container.push")
    def test_given_pebble_ready_when_certificate_available_then_certificate_and_key_are_pushed_to_workload(  # noqa: E501
        self, patch_push, patch_container_file_exists
    ):
        patch_container_file_exists.return_value = False
        common_name = "whatever.domain"
        certificate = "whatever certificate"
        private_key = "whatever private key"
        ca_certificate = "whatever ca certificate"
        key_values = {"domain": common_name}
        self.harness.update_config(key_values=key_values)
        self.harness.container_pebble_ready("magma-orc8r-certifier")
        event = Mock()
        event.certificate_data = {
            "common_name": common_name,
            "cert": certificate,
            "key": private_key,
            "ca": ca_certificate,
        }

        self.harness.charm._on_certificate_available(event)

        calls = [
            call(path="/var/opt/magma/certs/rootCA.pem", source=ca_certificate),
            call(path="/var/opt/magma/certs/controller.crt", source=certificate),
            call(path="/var/opt/magma/certs/controller.key", source=private_key),
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
