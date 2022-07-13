#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""magma-orc8r-orchestrator.

magma-orc8r-orchestrator provides data for configure of core gateway service configuration, metrics
and CRUD API.
"""


import logging
import re
from typing import Dict, Union

from charms.magma_orc8r_certifier.v0.cert_admin_operator import (
    CertAdminOperatorRequires,
    CertificateAvailableEvent,
)
from charms.observability_libs.v1.kubernetes_service_patch import (
    KubernetesServicePatch,
    ServicePort,
)
from lightkube import Client
from lightkube.resources.core_v1 import Service
from ops.charm import (
    ActionEvent,
    CharmBase,
    ConfigChangedEvent,
    InstallEvent,
    PebbleReadyEvent,
    RelationEvent,
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
from ops.pebble import APIError, ConnectionError, ExecError, Layer

logger = logging.getLogger(__name__)


class MagmaOrc8rOrchestratorCharm(CharmBase):
    """Main class that is instantiated everytime an event occurs."""

    BASE_CONFIG_PATH = "/var/opt/magma/configs/orc8r"
    BASE_CERTS_PATH = "/var/opt/magma/certs"

    # TODO: The various URL's should be provided through relationships
    PROMETHEUS_URL = "http://orc8r-prometheus:9090"
    PROMETHEUS_CACHE_GRPC_URL = "orc8r-prometheus-cache:9092"
    PROMETHEUS_CACHE_METRICS_URL = "http://orc8r-prometheus-cache:9091"
    ALERTMANAGER_URL = "http://orc8r-alertmanager:9093"

    def __init__(self, *args):
        """Initializes all event that need to be observed."""
        super().__init__(*args)
        self._container_name = self._service_name = "magma-orc8r-orchestrator"
        self._container = self.unit.get_container(self._container_name)
        self.cert_admin_operator = CertAdminOperatorRequires(self, "cert-admin-operator")
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[
                ServicePort(name="grpc", port=9180, targetPort=9112),
                ServicePort(name="http", port=8080, targetPort=10112),
            ],
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
            self.on.magma_orc8r_orchestrator_relation_joined,
            self._on_magma_orc8r_orchestrator_relation_joined,
        )
        self.framework.observe(
            self.on.create_orchestrator_admin_user_action,
            self._create_orchestrator_admin_user_action,
        )
        self.framework.observe(self.on.set_log_verbosity_action, self._set_log_verbosity_action)
        self.framework.observe(
            self.on.get_load_balancer_services_action,
            self._on_get_load_balancer_services_action,
        )
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_elasticsearch_url_config_changed)
        self.framework.observe(
            self.cert_admin_operator.on.certificate_available, self._on_certificate_available
        )

    @property
    def _environment_variables(self) -> dict:
        """Returns environment variables necessary to run main service and other cli commands.

        Returns:
            dict: Environment variables.
        """
        return {
            "SERVICE_HOSTNAME": self._container_name,
            "SERVICE_REGISTRY_MODE": "k8s",
            "SERVICE_REGISTRY_NAMESPACE": self._namespace,
        }

    @property
    def _pebble_layer(self) -> Layer:
        """Returns pebble layer for workload service.

        Returns:
            Layer: Pebble layer
        """
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
                        "-logtostderr=true "
                        "-v=0",
                        "environment": self._environment_variables,
                    }
                },
            }
        )

    @property
    def _elasticsearch_config_is_valid(self) -> bool:
        """Returns whether elasticsearch config is valid.

        Returns:
            bool: True/False
        """
        elasticsearch_url = self.model.config.get("elasticsearch-url")
        if not elasticsearch_url:
            return False
        if re.match("^[a-zA-Z0-9._-]+:[0-9]+$", elasticsearch_url):
            return True
        else:
            return False

    @property
    def _service_is_running(self) -> bool:
        """Returns whether workload service is running.

        Returns:
            bool: True/False
        """
        if self._container.can_connect():
            try:
                self._container.get_service(self._service_name)
                return True
            except ModelError:
                pass
        return False

    def _update_relations(self) -> None:
        """Updates the magma-orc8r-orchestrator relations with the status of the workload service.

        Returns:
            None
        """
        if not self.unit.is_leader():
            return
        relations = self.model.relations[self.meta.name]
        for relation in relations:
            self._update_relation_active_status(
                relation=relation, is_active=self._service_is_running
            )

    @property
    def _namespace(self) -> str:
        """Returns Kubernetes namespace.

        Returns:
            str: Kubernetes namespace
        """
        return self.model.name

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
    def _cert_admin_operator_relation_created(self) -> bool:
        """Returns whether cert-admin-operator relation is created.

        Returns:
            bool: True/False
        """
        return self._relation_created("cert-admin-operator")

    @property
    def _metrics_relation_created(self) -> bool:
        """Returns whether metrics-endpoint relation is created.

        Returns:
            bool: True/False
        """
        return self._relation_created("metrics-endpoint")

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

    def _on_get_load_balancer_services_action(self, event: ActionEvent) -> None:
        """Triggered when the get-load-balancer action is executed.

        Args:
            event (ActionEvent): Juju event

        Returns:
            None
        """
        load_balancer_services = self._get_load_balancer_services()
        event.set_results(load_balancer_services)

    def _get_load_balancer_services(self) -> Dict[str, str]:
        """Returns all Load balancer service addresses.

        Returns:
            dict: All load balancer service addresses.
        """
        service_dict = dict()
        client = Client()
        service_list = client.list(res=Service, namespace=self._namespace)
        for service in service_list:
            service_name = service.metadata.name
            ingresses = service.status.loadBalancer.ingress
            if ingresses:
                ip = ingresses[0].ip
                hostname = ingresses[0].hostname
                if hostname:
                    service_dict[service_name] = hostname
                else:
                    service_dict[service_name] = ip
        return service_dict

    def _on_install(self, event: InstallEvent) -> None:
        if not self._container.can_connect():
            event.defer()
            return
        self._write_config_files()

    def _write_config_files(self) -> None:
        """Pushes config files for orchestrator, metricsd and analytics to workload.

        Returns:
            None
        """
        self._write_orchestrator_config()
        self._write_metricsd_config()
        self._write_analytics_config()

    def _write_orchestrator_config(self) -> None:
        """Pushes orchestrator.yml config file to workload.

        Returns:
            None
        """
        orchestrator_config = (
            f'"prometheusGRPCPushAddress": "{self.PROMETHEUS_CACHE_GRPC_URL}"\n'
            '"prometheusPushAddresses":\n'
            f'- "{self.PROMETHEUS_CACHE_METRICS_URL}/metrics"\n'
            '"useGRPCExporter": true\n'
        )
        self._container.push(f"{self.BASE_CONFIG_PATH}/orchestrator.yml", orchestrator_config)

    def _write_metricsd_config(self) -> None:
        """Pushes metricsd.yml to workload.

        Returns:
            None
        """
        metricsd_config = (
            f'prometheusQueryAddress: "{self.PROMETHEUS_URL}"\n'
            f'alertmanagerApiURL: "{self.ALERTMANAGER_URL}/api/v2"\n'
            '"profile": "prometheus"\n'
        )
        self._container.push(f"{self.BASE_CONFIG_PATH}/metricsd.yml", metricsd_config)

    def _write_analytics_config(self) -> None:
        """Pushes analytics.yml to workload.

        Returns:
            None
        """
        analytics_config = (
            '"appID": ""\n'
            '"appSecret": ""\n'
            '"categoryName": "magma"\n'
            '"exportMetrics": false\n'
            '"metricExportURL": ""\n'
            '"metricsPrefix": ""\n'
        )
        self._container.push(f"{self.BASE_CONFIG_PATH}/analytics.yml", analytics_config)

    def _write_elastic_config(self) -> None:
        """Pushes elasticsearch config to workload.

        Returns:
            None
        """
        logging.info("Writing elasticsearch config to elastic.yml")
        elasticsearch_url, elasticsearch_port = self._get_elasticsearch_config()
        elastic_config = (
            f'"elasticHost": "{elasticsearch_url}"\n' f'"elasticPort": {elasticsearch_port}\n'
        )
        self._container.push(f"{self.BASE_CONFIG_PATH}/elastic.yml", elastic_config)

    def _on_elasticsearch_url_config_changed(self, event: ConfigChangedEvent) -> None:
        """Triggered when there is a Juju configuration changed.

        Will try to push the new elasticsearch config to the workload and restart the workload
        service.

        Args:
            event (ConfigChangedEvent): Juju event

        Returns:
            None
        """
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

    def _create_orchestrator_admin_user_action(self, event: ActionEvent) -> None:
        """Triggered when the create-orchestrator-admin-user action is executed.

        Args:
            event (ActionEvent): Juju event

        Returns:
            None
        """
        process = self._container.exec(
            [
                "/var/opt/magma/bin/accessc",
                "add-existing",
                "-admin",
                "-cert",
                "/var/opt/magma/certs/admin_operator.pem",
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
            for line in e.stderr.splitlines():  # type: ignore[union-attr]
                logger.error("    %s", line)

    def _set_log_verbosity_action(self, event: ActionEvent) -> None:
        """Triggered when the set-log-verbosity action is executed.

        Args:
            event (ActionEvent): Juju event

        Returns:
            None
        """
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
            for line in e.stderr.splitlines():  # type: ignore[union-attr]
                logger.error("    %s", line)

    def _on_magma_orc8r_orchestrator_pebble_ready(
        self, event: Union[PebbleReadyEvent, CertificateAvailableEvent]
    ) -> None:
        """Triggered when pebble is ready.

        Args:
            event (PebbleReadyEvent): Juju event

        Returns:
            None
        """
        if not self._metrics_relation_created:
            self.unit.status = BlockedStatus("Waiting for metrics-endpoint relation to be created")
            event.defer()
            return
        if not self._cert_admin_operator_relation_created:
            self.unit.status = BlockedStatus(
                "Waiting for cert-admin-operator relation to be created"
            )
            event.defer()
            return
        if not self._certs_are_stored:
            self.unit.status = WaitingStatus("Waiting for certs to be available")
            event.defer()
            return
        self._configure_orc8r(event)

    def _configure_orc8r(self, event: Union[PebbleReadyEvent, CertificateAvailableEvent]) -> None:
        """Adds layer to pebble config if the proposed config is different from the current one.

        Args:
            event (PebbleReadyEvent, CertificateAvailableEvent): Juju event

        Returns:
            None
        """
        try:
            plan = self._container.get_plan()
            if plan.services != self._pebble_layer.services:
                self.unit.status = MaintenanceStatus(
                    f"Configuring pebble layer for {self._service_name}"
                )
                self._container.add_layer(self._container_name, self._pebble_layer, combine=True)
                self._container.restart(self._service_name)
                logger.info(f"Restarted container {self._service_name}")
                self._update_relations()
                self.unit.status = ActiveStatus()
        except ConnectionError:
            logger.error(
                f"Could not restart {self._service_name} -- Pebble socket does "
                f"not exist or is not responsive"
            )

    def _get_elasticsearch_config(self) -> tuple:
        """Returns elasticsearch url and port based on juju config.

        Returns:
            tuple: Elasticsearch url and port.
        """
        elasticsearch_url = self.model.config.get("elasticsearch-url")
        if elasticsearch_url:
            elasticsearch_url_split = elasticsearch_url.split(":")
            return elasticsearch_url_split[0], elasticsearch_url_split[1]
        else:
            raise ValueError("The elasticsearch-url config is empty.")

    def _on_magma_orc8r_orchestrator_relation_joined(self, event: RelationEvent) -> None:
        """Triggered when charms join the orc8r-orchestrator relation.

        Args:
            event (RelationEvent): Juju event

        Returns:
            None
        """
        self._update_relations()
        if not self._service_is_running:
            event.defer()
            return

    def _update_relation_active_status(self, relation: Relation, is_active: bool) -> None:
        """Updates orc8r-orchestrator relation data content with workload service status.

        Args:
            relation: Juju relation
            is_active: True/False

        Returns:
            None
        """
        relation.data[self.unit].update(
            {
                "active": str(is_active),
            }
        )

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
        self._on_magma_orc8r_orchestrator_pebble_ready(event)


if __name__ == "__main__":
    main(MagmaOrc8rOrchestratorCharm)
