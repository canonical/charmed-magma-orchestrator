# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, PropertyMock, call, patch

from ops import testing
from ops.model import BlockedStatus
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
    def setUp(self):
        self.harness = testing.Harness(MagmaOrc8rCertifierCharm)
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

    @patch("charm.MagmaOrc8rCertifierCharm._certs_are_stored")
    @patch("charm.MagmaOrc8rCertifierCharm._get_db_connection_string", new_callable=PropertyMock)
    @patch("charm.MagmaOrc8rCertifierCharm._namespace", new_callable=PropertyMock)
    @patch("charm.MagmaOrc8rCertifierCharm._certificates_relation_created")
    @patch("charm.MagmaOrc8rCertifierCharm._db_relation_created")
    @patch("charm.MagmaOrc8rCertifierCharm._db_relation_established")
    def test_given_pebble_ready_when_get_plan_then_plan_is_filled_with_magma_orc8r_certifier_service_content(  # noqa: E501
        self,
        db_relation_established,
        db_relation_created,
        certificates_relation_created,
        patch_namespace,
        patch_db_string,
        patch_certs_stored,
    ):
        namespace = "whatever"
        patch_certs_stored.return_value = True
        db_relation_established.return_value = True
        db_relation_created.return_value = True
        certificates_relation_created.return_value = True
        patch_namespace.return_value = namespace
        patch_db_string.return_value = self.TEST_DB_CONNECTION_STRING
        key_values = {"domain": "whatever domain"}
        self.harness.update_config(key_values=key_values)

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
                        "SERVICE_REGISTRY_NAMESPACE": namespace,
                    },
                }
            },
        }
        updated_plan = self.harness.get_container_pebble_plan("magma-orc8r-certifier").to_dict()
        self.assertEqual(expected_plan, updated_plan)

    @patch("ops.model.Container.push")
    def test_given_pebble_ready_when_install_then_metricsd_config_file_is_created(
        self, patch_push
    ):
        self.harness.container_pebble_ready("magma-orc8r-certifier")
        self.harness.charm.on.install.emit()

        calls = [
            call(
                "/var/opt/magma/configs/orc8r/metricsd.yml",
                'prometheusQueryAddress: "http://orc8r-prometheus:9090"\n'
                'alertmanagerApiURL: "http://orc8r-alertmanager:9093/api/v2"\n'
                'prometheusConfigServiceURL: "http://orc8r-prometheus:9100/v1"\n'
                'alertmanagerConfigServiceURL: "http://orc8r-alertmanager:9101/v1"\n'
                '"profile": "prometheus"\n',
            ),
        ]
        patch_push.assert_has_calls(calls)

    def test_given_default_domain_config_when_config_changed_then_status_is_blocked(self):
        key_values = {"domain": ""}
        self.harness.container_pebble_ready("magma-orc8r-certifier")

        self.harness.update_config(key_values=key_values)

        assert self.harness.charm.unit.status == BlockedStatus("Config 'domain' is not valid")

    @patch(
        "charms.tls_certificates_interface.v0.tls_certificates.InsecureCertificatesRequires.request_certificate"  # noqa: E501,W505
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

        calls = [call(cert_type="server", common_name=common_name)]
        patch_request_certificates.assert_has_calls(calls)

    @patch(
        "charms.tls_certificates_interface.v0.tls_certificates.InsecureCertificatesRequires.request_certificate"  # noqa: E501,W505
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

    @patch("ops.model.Container.push")
    def test_given_pebble_ready_when_certificate_available_then_certificate_and_key_are_pushed_to_workload(  # noqa: E501
        self, patch_push
    ):
        common_name = "whatever.domain"
        certificate = "whatever certificate"
        private_key = "whatever private key"
        key_values = {"domain": common_name}
        self.harness.update_config(key_values=key_values)
        self.harness.container_pebble_ready("magma-orc8r-certifier")
        event = Mock()
        event.certificate_data = {
            "common_name": common_name,
            "cert": certificate,
            "key": private_key,
        }

        self.harness.charm._on_certificate_available(event)

        calls = [
            call("/var/opt/magma/certs/certifier.pem", certificate),
            call("/var/opt/magma/certs/certifier.key", private_key),
        ]
        patch_push.assert_has_calls(calls)
