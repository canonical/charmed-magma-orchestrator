#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Constants used in integration testing of magma orc8r."""

from pathlib import Path

import yaml

ACCESSD_METADATA = yaml.safe_load(
    Path("../orc8r-accessd-operator/metadata.yaml").read_text()
)
BOOTSTRAPPER_METADATA = yaml.safe_load(
    Path("../orc8r-bootstrapper-operator/metadata.yaml").read_text()
)
CERTIFIER_METADATA = yaml.safe_load(
    Path("../orc8r-certifier-operator/metadata.yaml").read_text()
)
NMS_MAGMALTE_METADATA = yaml.safe_load(
    Path("../nms-magmalte-operator/metadata.yaml").read_text()
)
OBSIDIAN_METADATA = yaml.safe_load(
    Path("../orc8r-obsidian-operator/metadata.yaml").read_text()
)
ORCHESTRATOR_METADATA = yaml.safe_load(
    Path("../orc8r-orchestrator-operator/metadata.yaml").read_text()
)
SERVICE_REGISTRY_METADATA = yaml.safe_load(
    Path("../orc8r-service-registry-operator/metadata.yaml").read_text()
)

ACCESSD_APPLICATION_NAME = "orc8r-accessd"
ACCESSD_CHARM_NAME = "magma-orc8r-accessd"
ACCESSD_CHARM_FILE_NAME = "magma-orc8r-accessd_ubuntu-22.04-amd64.charm"

ALERTMANAGER_K8S_CHARM_NAME = "alertmanager-k8s"
ALERTMANAGER_CONFIGURER_CHARM_NAME = "orc8r-alertmanager-configurer"

BOOTSTRAPPER_APPLICATION_NAME = "orc8r-bootstrapper"
BOOTSTRAPPER_CHARM_NAME = "magma-orc8r-bootstrapper"
BOOTSTRAPPER_CHARM_FILE_NAME = (
    "magma-orc8r-bootstrapper_ubuntu-22.04-amd64.charm"  # noqa: E501
)

CERTIFIER_APPLICATION_NAME = "orc8r-certifier"
CERTIFIER_CHARM_NAME = "magma-orc8r-certifier"
CERTIFIER_CHARM_FILE_NAME = "magma-orc8r-certifier_ubuntu-22.04-amd64.charm"

DB_CHARM_NAME = "postgresql-k8s"

GRAFANA_K8S_CHARM_NAME = "grafana-k8s"

NMS_MAGMALTE_APPLICATION_NAME = "nms-magmalte"
NMS_MAGMALTE_CHARM_NAME = "magma-nms-magmalte"
NMS_MAGMALTE_CHARM_FILE_NAME = "magma-nms-magmalte_ubuntu-22.04-amd64.charm"


OBSIDIAN_APPLICATION_NAME = "orc8r-obsidian"
OBSIDIAN_CHARM_NAME = "magma-orc8r-obsidian"
OBSIDIAN_CHARM_FILE_NAME = "magma-orc8r-obsidian_ubuntu-22.04-amd64.charm"  # noqa: E501

ORCHESTRATOR_APPLICATION_NAME = "orc8r-orchestrator"
ORCHESTRATOR_CHARM_NAME = "magma-orc8r-orchestrator"
ORCHESTRATOR_CHARM_FILE_NAME = (
    "magma-orc8r-orchestrator_ubuntu-22.04-amd64.charm"  # noqa: E501
)

PROMETHEUS_K8S_CHARM_NAME = "prometheus-k8s"
PROMETHEUS_CONFIGURER_K8S_CHARM_NAME = "prometheus-configurer-k8s"
PROMETHEUS_CACHE_APPLICATION_NAME = "orc8r-prometheus-cache"
PROMETHEUS_CACHE_CHARM_NAME = "prometheus-edge-hub"

SERVICE_REGISTRY_APPLICATION_NAME = "orc8r-service-registry"
SERVICE_REGISTRY_CHARM_NAME = "magma-orc8r-service-registry"
SERVICE_REGISTRY_CHARM_FILE_NAME = (
    "magma-orc8r-service-registry_ubuntu-22.04-amd64.charm"
)

TLS_CERTIFICATES_CHARM_NAME = "tls-certificates-operator"


DB_REQUIRER_ORC8R_CHARMS = [
    CERTIFIER_APPLICATION_NAME,
    NMS_MAGMALTE_APPLICATION_NAME,
    ACCESSD_APPLICATION_NAME,
    BOOTSTRAPPER_APPLICATION_NAME,
]
