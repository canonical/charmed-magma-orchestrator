#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
import yaml
from pathlib import Path

CERTIFIER_METADATA = yaml.safe_load(
    Path("../orc8r-certifier-operator/metadata.yaml").read_text())
NMS_MAGMALTE_METADATA = yaml.safe_load(
    Path("../nms-magmalte-operator/metadata.yaml").read_text())
ORCHESTRATOR_METADATA = yaml.safe_load(
    Path("../orc8r-orchestrator-operator/metadata.yaml").read_text()
)
ACCESSD_METADATA = yaml.safe_load(
    Path("../orc8r-accessd-operator/metadata.yaml").read_text())
SERVICE_REGISTRY_METADATA = yaml.safe_load(
    Path("../orc8r-service-registry-operator/metadata.yaml").read_text()
)
BOOTSTRAPPER_METADATA = yaml.safe_load(
    Path("../orc8r-bootstrapper-operator/metadata.yaml").read_text()
)
OBSIDIAN_METADATA = yaml.safe_load(
    Path("../orc8r-obsidian-operator/metadata.yaml").read_text())

CERTIFIER_APPLICATION_NAME = "orc8r-certifier"
CERTIFIER_CHARM_NAME = "magma-orc8r-certifier"
CERTIFIER_CHARM_FILE_NAME = "magma-orc8r-certifier_ubuntu-22.04-amd64.charm"
DB_APPLICATION_NAME = "postgresql-k8s"
NMS_MAGMALTE_APPLICATION_NAME = "nms-magmalte"
NMS_MAGMALTE_CHARM_NAME = "magma-nms-magmalte"
NMS_MAGMALTE_CHARM_FILE_NAME = "magma-nms-magmalte_ubuntu-22.04-amd64.charm"
ORCHESTRATOR_APPLICATION_NAME = "orc8r-orchestrator"
ORCHESTRATOR_CHARM_NAME = "magma-orc8r-orchestrator"
ORCHESTRATOR_CHARM_FILE_NAME = "magma-orc8r-orchestrator_ubuntu-22.04-amd64.charm"
ACCESSD_APPLICATION_NAME = "orc8r-accessd"
ACCESSD_CHARM_NAME = "magma-orc8r-accessd"
ACCESSD_CHARM_FILE_NAME = "magma-orc8r-accessd_ubuntu-22.04-amd64.charm"
SERVICE_REGISTRY_APPLICATION_NAME = "orc8r-service-registry"
SERVICE_REGISTRY_CHARM_NAME = "magma-orc8r-service-registry"
SERVICE_REGISTRY_CHARM_FILE_NAME = "magma-orc8r-service-registry_ubuntu-22.04-amd64.charm"
BOOTSTRAPPER_APPLICATION_NAME = "orc8r-bootstrapper"
BOOTSTRAPPER_CHARM_NAME = "magma-orc8r-bootstrapper"
BOOTSTRAPPER_CHARM_FILE_NAME = "magma-orc8r-bootstrapper_ubuntu-22.04-amd64.charm"
OBSIDIAN_APPLICATION_NAME = "orc8r-obsidian"
OBSIDIAN_CHARM_NAME = "magma-orc8r-obsidian"
OBSIDIAN_CHARM_FILE_NAME = "magma-orc8r-obsidian_ubuntu-22.04-amd64.charm"
