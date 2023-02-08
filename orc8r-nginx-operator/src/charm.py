#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Proxies traffic between nms and obsidian."""

import logging
import re
from typing import List, Optional, Union

from charms.magma_orc8r_certifier.v0.cert_certifier import CertCertifierRequires
from charms.magma_orc8r_certifier.v0.cert_certifier import (
    CertificateAvailableEvent as CertifierCertificateAvailableEvent,
)
from charms.magma_orc8r_certifier.v0.cert_controller import CertControllerRequires
from charms.magma_orc8r_certifier.v0.cert_controller import (
    CertificateAvailableEvent as ControllerCertificateAvailableEvent,
)
from charms.magma_orc8r_certifier.v0.cert_root_ca import (
    CertificateAvailableEvent as RootCACertificateAvailableEvent,
)
from charms.magma_orc8r_certifier.v0.cert_root_ca import CertRootCARequires
from charms.magma_orchestrator_interface.v0.magma_orchestrator_interface import (
    OrchestratorProvides,
)
from charms.observability_libs.v1.kubernetes_service_patch import KubernetesServicePatch
from httpx import HTTPStatusError
from lightkube import Client
from lightkube.models.core_v1 import ServicePort, ServiceSpec
from lightkube.models.meta_v1 import ObjectMeta
from lightkube.resources.core_v1 import Service
from ops.charm import (
    CharmBase,
    ConfigChangedEvent,
    InstallEvent,
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
from ops.pebble import ExecError, Layer, PathError, ProtocolError

logger = logging.getLogger(__name__)


class MagmaOrc8rNginxCharm(CharmBase):
    """An instance of this object everytime an event occurs."""

    BASE_CERTS_PATH = "/var/opt/magma/certs"
    REQUIRED_RELATIONS = ["cert-certifier", "cert-controller"]
    REQUIRED_MAGMA_SERVICES_RELATIONS = ["magma-orc8r-bootstrapper", "magma-orc8r-obsidian"]

    def __init__(self, *args):
        """Initializes all event that need to be observed."""
        super().__init__(*args)
        self._container_name = self._service_name = "magma-orc8r-nginx"
        self._container = self.unit.get_container(self._container_name)
        self._cert_certifier = CertCertifierRequires(self, "cert-certifier")
        self._cert_controller = CertControllerRequires(self, "cert-controller")
        self._cert_root_ca = CertRootCARequires(self, "cert-root-ca")
        self.orchestrator_provider = OrchestratorProvides(self, "orchestrator")
        self.service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[
                ServicePort(name="health", port=80),
                ServicePort(name="clientcert", port=8443),
                ServicePort(name="open", port=8444),
                ServicePort(name="api", port=443, targetPort=9443),
            ],
            service_type="LoadBalancer",
            service_name="orc8r-nginx-proxy",
            additional_labels={"app.kubernetes.io/part-of": "orc8r"},
            additional_selectors={"app.kubernetes.io/name": "orc8r-nginx"},
        )

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(
            self.on.magma_orc8r_nginx_pebble_ready, self._configure_magma_orc8r_nginx
        )
        self.framework.observe(
            self.on.magma_orc8r_nginx_relation_joined, self._on_magma_orc8r_nginx_relation_joined
        )
        self.framework.observe(
            self.on.orchestrator_relation_joined,
            self._publish_orchestrator_details_in_the_relation_data_bag,
        )
        self.framework.observe(self.on.remove, self._on_remove)

        self.framework.observe(
            self._cert_certifier.on.certificate_available, self._on_certifier_certificate_available
        )
        self.framework.observe(
            self._cert_controller.on.certificate_available,
            self._on_controller_certificate_available,
        )
        self.framework.observe(
            self._cert_root_ca.on.certificate_available, self._on_root_ca_certificate_available
        )
        for required_rel in self.REQUIRED_MAGMA_SERVICES_RELATIONS:
            self.framework.observe(
                self.on[required_rel].relation_broken, self._on_required_relation_broken
            )

        for required_rel in self.REQUIRED_MAGMA_SERVICES_RELATIONS:
            self.framework.observe(
                self.on[required_rel].relation_joined, self._configure_magma_orc8r_nginx
            )

    def _on_install(self, event: InstallEvent) -> None:
        """Triggerred once when charm is installed.

        Args:
            event: Juju event (InstallEvent)
        """
        if not self._container.can_connect():
            logger.info("Can't connect to container - Deferring")
            event.defer()
            return
        self._generate_nginx_config()
        self._create_additional_orc8r_nginx_services()

    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        """Triggered when configuration is changed.

        Args:
            event: Juju event
        """
        if not self._domain_config_is_valid:
            self.unit.status = BlockedStatus("Domain config is not valid")
            return
        if not self._container.can_connect():
            logger.info("Can't connect to container - Deferring")
            event.defer()
            return
        self._generate_nginx_config()
        self._configure_magma_orc8r_nginx(event)
        if self.model.relations.get("orchestrator"):
            self._publish_orchestrator_details_in_the_relation_data_bag(event)

    def _configure_magma_orc8r_nginx(
        self,
        event: Union[
            PebbleReadyEvent,
            CertifierCertificateAvailableEvent,
            ControllerCertificateAvailableEvent,
            ConfigChangedEvent,
            RootCACertificateAvailableEvent,
        ],
    ) -> None:
        """Triggerred when pebble ready.

        Args:
            event: Juju event
        """
        if not self._domain_config_is_valid:
            self.unit.status = BlockedStatus("Domain config is not valid")
            return
        if not self._relations_created:
            event.defer()
            return
        if not self._relations_ready:
            event.defer()
            return
        if not self._certs_are_stored:
            self.unit.status = WaitingStatus("Waiting for certificates to be available.")
            event.defer()
            return
        self._configure_pebble_layer(event)

    def _on_magma_orc8r_nginx_relation_joined(self, event: RelationJoinedEvent) -> None:
        """Event handler for magma-orc8r-nginx RelationJoinedEvent.

        Updates the status of the `orc8r-nginx` service in the relation data bags so that relation
        consumers know if it's running or not. If `orc8r-nginx` is not running, event is also
        deferred.

        Args:
            event (RelationJoinedEvent): Juju event
        """
        self._update_relations()
        if not self._service_is_running:
            event.defer()
            return

    def _publish_orchestrator_details_in_the_relation_data_bag(
        self,
        event: Union[
            ConfigChangedEvent,
            RelationJoinedEvent,
            RootCACertificateAvailableEvent,
            CertifierCertificateAvailableEvent,
        ],
    ) -> None:
        """Publishes Orchestrator details inside the `orchestrator` relation data bag.

        Args:
            event: Juju event (ConfigChangedEvent, RelationJoinedEvent
                   or RootCACertificateAvailableEvent)
        """
        if not self.unit.is_leader():
            return
        if not self._domain_config_is_valid:
            self.unit.status = BlockedStatus("Domain config is not valid")
            event.defer()
            return
        if not self._service_is_running:
            self.unit.status = WaitingStatus(
                f"Waiting for {self._service_name} service to become active"
            )
            event.defer()
            return
        if not self._cert_is_stored(f"{self.BASE_CERTS_PATH}/rootCA.pem"):
            self.unit.status = WaitingStatus("Waiting for rootCA certificate to be available")
            event.defer()
            return
        if not self._cert_is_stored(f"{self.BASE_CERTS_PATH}/certifier.pem"):
            self.unit.status = WaitingStatus(
                "Waiting for `certifier.pem` certificate to be available"
            )
            event.defer()
            return
        try:
            rootca_cert = self._container.pull(f"{self.BASE_CERTS_PATH}/rootCA.pem")
            certifier_pem = self._container.pull(f"{self.BASE_CERTS_PATH}/certifier.pem")
        except (PathError, ProtocolError):
            self.unit.status = BlockedStatus("Failed to pull certs from the container")
            event.defer()
            return
        self.orchestrator_provider.set_orchestrator_information(
            root_ca_certificate=rootca_cert.read(),  # type: ignore[arg-type]
            certifier_pem_certificate=certifier_pem.read(),  # type: ignore[arg-type]
            orchestrator_address=f"controller.{self._domain_config}",
            orchestrator_port=443,
            bootstrapper_address=f"bootstrapper-controller.{self._domain_config}",
            bootstrapper_port=443,
            fluentd_address=f"fluentd.{self._domain_config}",
            fluentd_port=24224,
        )

    def _on_remove(self, _) -> None:
        """Remove additional magma-orc8r-nginx services."""
        client = Client()
        for service in self._magma_orc8r_nginx_additional_services:
            client.delete(Service, name=service.metadata.name, namespace=self._namespace)

    def _on_certifier_certificate_available(
        self, event: CertifierCertificateAvailableEvent
    ) -> None:
        """Triggered when certifier certificate is available.

        Args:
            event (CertifierCertificateAvailableEvent): Juju event
        """
        logger.info("Certifier certificate available")
        if not self._container.can_connect():
            logger.info("Can't connect to container - Deferring")
            event.defer()
            return
        self._container.push(
            path=f"{self.BASE_CERTS_PATH}/certifier.pem", source=event.certificate
        )
        self._configure_magma_orc8r_nginx(event)
        if self.model.relations.get("orchestrator"):
            self._publish_orchestrator_details_in_the_relation_data_bag(event)

    def _on_controller_certificate_available(
        self, event: ControllerCertificateAvailableEvent
    ) -> None:
        """Triggered when controller certificate is available.

        Args:
            event (ControllerCertificateAvailableEvent): Juju event
        """
        logger.info("Controller certificate available")
        if not self._container.can_connect():
            logger.info("Can't connect to container - Deferring")
            event.defer()
            return
        self._container.push(
            path=f"{self.BASE_CERTS_PATH}/controller.crt", source=event.certificate
        )
        self._container.push(
            path=f"{self.BASE_CERTS_PATH}/controller.key", source=event.private_key
        )
        self._configure_magma_orc8r_nginx(event)

    def _on_root_ca_certificate_available(self, event: RootCACertificateAvailableEvent) -> None:
        """Triggered when rootCA certificate is available.

        Stores the rootCA certificate in the workload container's storage.

        Args:
            event (RootCACertificateAvailableEvent): Juju event
        """
        logger.info("rootCA certificate available")
        if not self._container.can_connect():
            logger.info("Can't connect to container - Deferring")
            event.defer()
            return
        self._container.push(path=f"{self.BASE_CERTS_PATH}/rootCA.pem", source=event.certificate)
        self._configure_magma_orc8r_nginx(event)
        if self.model.relations.get("orchestrator"):
            self._publish_orchestrator_details_in_the_relation_data_bag(event)

    def _on_required_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Triggered on relation broken events, sets the status of the charm to blocked.

        Args:
            event(RelationBrokenEvent): juju event
        """
        self.unit.status = BlockedStatus(
            f"Waiting for relation(s) to be created: {event.relation.name}"
        )

    def _generate_nginx_config(self) -> None:
        """Generates nginx config to /etc/nginx/nginx.conf."""
        logger.info("Generating nginx config file...")
        domain_name = self.model.config.get("domain")
        process = self._container.exec(
            command=["/usr/local/bin/generate_nginx_configs.py"],
            environment={
                "PROXY_BACKENDS": f"{self._namespace}.svc.cluster.local",
                "CONTROLLER_HOSTNAME": f"controller.{domain_name}",
                "RESOLVER": "kube-dns.kube-system.svc.cluster.local valid=10s",
                "SERVICE_REGISTRY_MODE": "k8s",
            },
        )
        try:
            process.wait_output()
        except ExecError as error:
            raise ProcessExecutionError(error)
        logger.info("Successfully generated nginx config file")

    def _create_additional_orc8r_nginx_services(self) -> None:
        """Creates additional K8s services.

        Those services are expected to be delivered by the magma-orc8r-nginx service.
        """
        client = Client()
        logger.info("Creating additional magma-orc8r-nginx services")
        for service in self._magma_orc8r_nginx_additional_services:
            if not self._orc8r_nginx_service_created(service.metadata.name):
                logger.info(f"Creating {service.metadata.name} service")
                client.create(service)

    def _configure_pebble_layer(
        self,
        event: Union[
            PebbleReadyEvent,
            CertifierCertificateAvailableEvent,
            ControllerCertificateAvailableEvent,
            ConfigChangedEvent,
            RootCACertificateAvailableEvent,
        ],
    ) -> None:
        """Adds service to workload and restarts it.

        Args:
            event: Juju event
        """
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
            self.unit.status = ActiveStatus()
        else:
            self.unit.status = WaitingStatus(f"Waiting for {self._container} to be ready")
            event.defer()
            return

    def _update_relations(self) -> None:
        """Updates the status of the `orc8r-nginx` service.

        Updates the status of the `orc8r-nginx` service in the relation data bags so that relation
        consumers know if it's running or not.
        """
        if not self.unit.is_leader():
            return
        relations = self.model.relations[self.meta.name]
        for relation in relations:
            self._update_relation_active_status(
                relation=relation, is_active=self._service_is_running
            )

    def _update_relation_active_status(self, relation: Relation, is_active: bool) -> None:
        """Updates service status in the relation data bag.

        Args:
            relation: Juju Relation object to update
            is_active: Workload service status
        """
        relation.data[self.unit].update(
            {
                "active": str(is_active),
            }
        )

    def _orc8r_nginx_service_created(self, service_name: str) -> bool:
        """Checks whether given K8s service exists or not.

        Args:
            service_name (str): Kubernetes service name

        Returns:
            bool: True/False
        """
        client = Client()
        try:
            client.get(Service, name=service_name, namespace=self._namespace)
            return True
        except HTTPStatusError:
            return False

    @property
    def _magma_orc8r_nginx_additional_services(self) -> List[Service]:
        """Returns list of additional K8s services to be created by magma-orc8r-nginx."""
        return [
            Service(
                apiVersion="v1",
                kind="Service",
                metadata=ObjectMeta(
                    namespace=self._namespace,
                    name="orc8r-bootstrap-nginx",
                    labels={
                        "app.kubernetes.io/component": "nginx-proxy",
                        "app.kubernetes.io/part-of": "orc8r",
                    },
                ),
                spec=ServiceSpec(
                    selector={
                        "app.kubernetes.io/name": "orc8r-nginx",
                    },
                    ports=[
                        ServicePort(
                            name="health",
                            port=80,
                            targetPort=80,
                        ),
                        ServicePort(
                            name="open-legacy",
                            port=443,
                            targetPort=8444,
                        ),
                        ServicePort(
                            name="open",
                            port=8444,
                            targetPort=8444,
                        ),
                    ],
                    type="LoadBalancer",
                ),
            ),
            Service(
                apiVersion="v1",
                kind="Service",
                metadata=ObjectMeta(
                    namespace=self._namespace,
                    name="orc8r-clientcert-nginx",
                    labels={
                        "app.kubernetes.io/component": "nginx-proxy",
                        "app.kubernetes.io/part-of": "orc8r",
                    },
                ),
                spec=ServiceSpec(
                    selector={"app.kubernetes.io/name": "orc8r-nginx"},
                    ports=[
                        ServicePort(
                            name="health",
                            port=80,
                            targetPort=80,
                        ),
                        ServicePort(
                            name="clientcert-legacy",
                            port=443,
                            targetPort=8443,
                        ),
                        ServicePort(
                            name="clientcert",
                            port=8443,
                            targetPort=8443,
                        ),
                    ],
                    type="LoadBalancer",
                ),
            ),
        ]

    @property
    def _domain_config_is_valid(self) -> bool:
        """Returns whether the "domain" config is valid.

        Returns:
            bool: Whether the domain is a valid one.
        """
        domain = self.model.config.get("domain")
        if not domain:
            return False
        pattern = re.compile(
            r"^(?:[a-zA-Z0-9]"  # First character of the domain
            r"(?:[a-zA-Z0-9-_]{0,61}[A-Za-z0-9])?\.)"  # Sub domain + hostname
            r"+[A-Za-z0-9][A-Za-z0-9-_]{0,61}"  # First 61 characters of the gTLD
            r"[A-Za-z]$"  # Last character of the gTLD
        )
        if pattern.match(domain):
            return True
        return False

    @property
    def _relations_created(self) -> bool:
        """Checks whether required relations are created.

        Returns:
            bool: True/False
        """
        if missing_relations := [
            relation
            for relation in self.REQUIRED_RELATIONS + self.REQUIRED_MAGMA_SERVICES_RELATIONS
            if not self.model.get_relation(relation)
        ]:
            msg = f"Waiting for relation(s) to be created: {', '.join(missing_relations)}"
            self.unit.status = BlockedStatus(msg)
            return False
        return True

    @property
    def _relations_ready(self) -> bool:
        """Checks whether required relations are ready.

        Returns:
            bool: True/False
        """
        if missing_relations := [
            relation
            for relation in self.REQUIRED_MAGMA_SERVICES_RELATIONS
            if not self._relation_active(relation)
        ]:
            msg = f"Waiting for relation(s) to be ready: {', '.join(missing_relations)}"
            self.unit.status = WaitingStatus(msg)
            return False
        return True

    def _relation_active(self, relation_name: str) -> bool:
        """Checks whether related service is ready.

        Checks whether related service is running by checking the value of the `active` key
        provided in the relation data bag.

        Args:
            relation_name: The name of the relation

        Returns:
            bool: True/False
        """
        try:
            rel = self.model.get_relation(relation_name)
            units = rel.units  # type: ignore[union-attr]
            return rel.data[next(iter(units))]["active"] == "True"  # type: ignore[union-attr]
        except (AttributeError, KeyError, StopIteration):
            return False

    @property
    def _certs_are_stored(self) -> bool:
        """Checks whether the required certs are stored in the container.

        Returns:
            bool: True/False
        """
        if not self._container.can_connect():
            return False
        return all(
            [
                self._cert_is_stored(f"{self.BASE_CERTS_PATH}/controller.key"),
                self._cert_is_stored(f"{self.BASE_CERTS_PATH}/controller.crt"),
                self._cert_is_stored(f"{self.BASE_CERTS_PATH}/certifier.pem"),
                self._cert_is_stored(f"{self.BASE_CERTS_PATH}/rootCA.pem"),
            ]
        )

    def _cert_is_stored(self, cert_path: str) -> bool:
        """Checks whether given cert is stored in the container.

        Args:
            cert_path (str): Certificate path

        Returns:
            bool: True/False
        """
        return self._container.exists(cert_path)

    @property
    def _service_is_running(self) -> bool:
        """Checks whether the workload service is running.

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

    @property
    def _pebble_layer(self) -> Layer:
        """Returns pebble layer for the magma-orc8r-nginx service."""
        return Layer(
            {
                "summary": f"{self._service_name} pebble layer",
                "services": {
                    self._service_name: {
                        "override": "replace",
                        "startup": "enabled",
                        "command": "nginx -g 'daemon off;'",
                        "environment": {
                            "SERVICE_REGISTRY_MODE": "k8s",
                            "SERVICE_REGISTRY_NAMESPACE": self._namespace,
                        },
                    }
                },
            }
        )

    @property
    def _domain_config(self) -> Optional[str]:
        """Returns domain config.

        Returns:
            str: Domain config
        """
        return self.model.config.get("domain")

    @property
    def _namespace(self) -> str:
        """Returns k8s namespace (equivalent to Juju model name).

        Returns:
            str: K8s namespace.
        """
        return self.model.name


class ProcessExecutionError(Exception):
    """Custom error improving logging in case of ExecError."""

    def __init__(self, error: ExecError):
        """Print error details.

        Args:
            error (ExecError): Original error
        """
        logger.error(f"ERROR: Process exited with code {error.exit_code}.")
        if error.stderr:
            logger.error("Stderr:")
            for line in error.stderr.splitlines():
                logger.error(f"    {str(line)}")


if __name__ == "__main__":
    main(MagmaOrc8rNginxCharm)
