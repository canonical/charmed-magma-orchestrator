#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import re

from charms.magma_orc8r_certifier.v0.cert_admin_operator import CertAdminOperatorRequires
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import APIError, ConnectionError, ExecError, Layer

logger = logging.getLogger(__name__)


class MagmaOrc8rOrchestratorCharm(CharmBase):

    BASE_CONFIG_PATH = "/var/opt/magma/configs/orc8r"
    BASE_CERTS_PATH = "/var/opt/magma/certs"

    # TODO: The various URL's should be provided through relationships
    PROMETHEUS_URL = "http://orc8r-prometheus:9090"
    PROMETHEUS_CONFIGURER_URL = "http://orc8r-prometheus:9100"
    PROMETHEUS_CACHE_GRPC_URL = "orc8r-prometheus-cache:9092"
    PROMETHEUS_CACHE_METRICS_URL = "http://orc8r-prometheus-cache:9091"
    ALERTMANAGER_URL = "http://orc8r-alertmanager:9093"
    ALERTMANAGER_CONFIGURER_URL = "http://orc8r-alertmanager:9101"

    def __init__(self, *args):
        """An instance of this object everytime an event occurs."""
        super().__init__(*args)
        self._admin_operator = CertAdminOperatorRequires(self, "cert-admin-operator")
        self._container_name = self._service_name = "magma-orc8r-orchestrator"
        self._container = self.unit.get_container(self._container_name)
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[("grpc", 9180, 9112), ("http", 8080, 10112)],
            additional_labels={
                "app.kubernetes.io/part-of": "orc8r-app",
                "orc8r.io/analytics_collector": "true",
                "orc8r.io/mconfig_builder": "true",
                "orc8r.io/metrics_exporter": "true",
                "orc8r.io/obsidian_handlers": "true",
                "orc8r.io/state_indexer": "true",
                "orc8r.io/stream_provider": "true",
                "orc8r.io/swagger_spec": "true",
            },
            additional_annotations={
                "orc8r.io/state_indexer_types": "directory_record",
                "orc8r.io/state_indexer_version": "1",
                "orc8r.io/stream_provider_streams": "configs",
                "orc8r.io/obsidian_handlers_path_prefixes": "/, "
                "/magma/v1/channels, "
                "/magma/v1/networks, "
                "/magma/v1/networks/:network_id,",
            },
        )
        self.framework.observe(
            self.on.magma_orc8r_orchestrator_pebble_ready,
            self._on_magma_orc8r_orchestrator_pebble_ready,
        )
        self.framework.observe(
            self.on.create_orchestrator_admin_user_action,
            self._create_orchestrator_admin_user_action,
        )
        self.framework.observe(self.on.set_log_verbosity_action, self._set_log_verbosity_action)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_elasticsearch_url_config_changed)
        self.framework.observe(
            self._admin_operator.on.certificate_available, self._on_certificate_available
        )

    def _on_install(self, event):
        if not self._container.can_connect():
            event.defer()
            return
        self._write_config_files()

    def _on_certificate_available(self, event):
        logger.info("Admin Operator certificate available")
        if not self._container.can_connect():
            logger.info("Can't connect to container - Deferring")
            event.defer()
            return
        self._container.push(
            path=f"{self.BASE_CERTS_PATH}/admin_operator.pem", source=event.certificate
        )
        self._on_magma_orc8r_orchestrator_pebble_ready(event)

    def _write_config_files(self):
        self._write_orchestrator_config()
        self._write_metricsd_config()
        self._write_analytics_config()

    def _write_orchestrator_config(self):
        orchestrator_config = (
            f'"prometheusGRPCPushAddress": "{self.PROMETHEUS_CACHE_GRPC_URL}"\n'
            '"prometheusPushAddresses":\n'
            f'- "{self.PROMETHEUS_CACHE_METRICS_URL}/metrics"\n'
            '"useGRPCExporter": true\n'
        )
        self._container.push(f"{self.BASE_CONFIG_PATH}/orchestrator.yml", orchestrator_config)

    def _write_metricsd_config(self):
        metricsd_config = (
            f'prometheusQueryAddress: "{self.PROMETHEUS_URL}"\n'
            f'alertmanagerApiURL: "{self.ALERTMANAGER_URL}/api/v2"\n'
            f'prometheusConfigServiceURL: "{self.PROMETHEUS_CONFIGURER_URL}/v1"\n'
            f'alertmanagerConfigServiceURL: "{self.ALERTMANAGER_CONFIGURER_URL}/v1"\n'
            '"profile": "prometheus"\n'
        )
        self._container.push(f"{self.BASE_CONFIG_PATH}/metricsd.yml", metricsd_config)

    def _write_analytics_config(self):
        analytics_config = (
            '"appID": ""\n'
            '"appSecret": ""\n'
            '"categoryName": "magma"\n'
            '"exportMetrics": false\n'
            '"metricExportURL": ""\n'
            '"metricsPrefix": ""\n'
        )
        self._container.push(f"{self.BASE_CONFIG_PATH}/analytics.yml", analytics_config)

    def _write_elastic_config(self):
        logging.info("Writing elasticsearch config to elastic.yml")
        elasticsearch_url, elasticsearch_port = self._get_elasticsearch_config()
        elastic_config = (
            f'"elasticHost": "{elasticsearch_url}"\n' f'"elasticPort": {elasticsearch_port}\n'
        )
        self._container.push(f"{self.BASE_CONFIG_PATH}/elastic.yml", elastic_config)

    def _on_elasticsearch_url_config_changed(self, event):
        # TODO: Elasticsearch url should be passed through a relationship (not a config)
        if not self._container.can_connect():
            event.defer()
            return
        if self._elasticsearch_config_is_valid:
            self._write_elastic_config()
            try:
                logger.info("Restarting service")
                self._container.restart(self._service_name)
                self.unit.status = ActiveStatus()
            except APIError:
                logger.info("Service is not yet started, doing nothing")
        else:
            self.unit.status = BlockedStatus(
                "Config for elasticsearch is not valid. Format should be <hostname>:<port>"
            )

    def _create_orchestrator_admin_user_action(self, event):
        process = self._container.exec(
            [
                "/var/opt/magma/bin/accessc",
                "add-existing",
                "-admin",
                "-cert",
                f"{self.BASE_CERTS_PATH}/admin_operator.pem",
                "admin_operator",
            ],
            timeout=30,
            environment=self._environment_variables,
            working_dir="/",
        )
        try:
            stdout, error = process.wait_output()
            logger.info(f"Return message: {stdout}, {error}")
        except ExecError as e:
            logger.error("Exited with code %d. Stderr:", e.exit_code)
            for line in e.stderr.splitlines():
                logger.error("    %s", line)

    def _set_log_verbosity_action(self, event):
        process = self._container.exec(
            [
                "/var/opt/magma/bin/service303_cli",
                "log_verbosity",
                str(event.params["level"]),
                event.params["service"],
            ],
            timeout=30,
            environment=self._environment_variables,
            working_dir="/",
        )
        try:
            stdout, error = process.wait_output()
            logger.info(f"Return message: {stdout}, {error}")
        except ExecError as e:
            logger.error("Exited with code %d. Stderr:", e.exit_code)
            for line in e.stderr.splitlines():
                logger.error("    %s", line)

    def _on_magma_orc8r_orchestrator_pebble_ready(self, event):
        if not self._admin_operator_relation_created:
            self.unit.status = BlockedStatus("Waiting for admin-operator relation to be created")
            event.defer()
            return
        if not self._admin_operator_cert_stored:
            self.unit.status = WaitingStatus("Waiting for admin-operator cert to be available")
            event.defer()
            return
        self._configure_orc8r(event)

    @property
    def _admin_operator_cert_stored(self) -> bool:
        return self._container.exists(f"{self.BASE_CERTS_PATH}/admin_operator.pem")

    @property
    def _admin_operator_relation_created(self) -> bool:
        return self._relation_created("cert-admin-operator")

    def _relation_created(self, relation_name: str) -> bool:
        if not self.model.get_relation(relation_name):
            return False
        return True

    def _configure_orc8r(self, event):
        """Adds layer to pebble config if the proposed config is different from the current one."""
        try:
            plan = self._container.get_plan()
            if plan.services != self._pebble_layer.services:
                self.unit.status = MaintenanceStatus(
                    f"Configuring pebble layer for {self._service_name}"
                )
                self._container.add_layer(self._container_name, self._pebble_layer, combine=True)
                self._container.restart(self._service_name)
                logger.info(f"Restarted container {self._service_name}")
                self.unit.status = ActiveStatus()
        except ConnectionError:
            logger.error(
                f"Could not restart {self._service_name} -- Pebble socket does "
                f"not exist or is not responsive"
            )

    @property
    def _environment_variables(self) -> dict:
        return {
            "SERVICE_HOSTNAME": self._container_name,
            "SERVICE_REGISTRY_MODE": "k8s",
            "SERVICE_REGISTRY_NAMESPACE": self._namespace,
        }

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
                        "/var/opt/magma/bin/orchestrator "
                        "-run_echo_server=true "
                        "-logtostderr=true -v=0",
                        "environment": self._environment_variables,
                    }
                },
            }
        )

    def _get_elasticsearch_config(self) -> tuple:
        elasticsearch_url = self.model.config.get("elasticsearch-url")
        elasticsearch_url_split = elasticsearch_url.split(":")  # type: ignore[union-attr]
        return elasticsearch_url_split[0], elasticsearch_url_split[1]

    @property
    def _elasticsearch_config_is_valid(self) -> bool:
        elasticsearch_url = self.model.config.get("elasticsearch-url")
        if not elasticsearch_url:
            return False
        if re.match("^[a-zA-Z0-9._-]+:[0-9]+$", elasticsearch_url):
            return True
        else:
            return False

    @property
    def _namespace(self) -> str:
        return self.model.name


if __name__ == "__main__":
    main(MagmaOrc8rOrchestratorCharm)
