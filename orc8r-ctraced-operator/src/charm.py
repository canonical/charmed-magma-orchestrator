#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Handles gateway call traces, exposing this functionality via a CRUD API."""

from charms.magma_orc8r_libs.v0.orc8r_base_db import Orc8rBase
from charms.observability_libs.v1.kubernetes_service_patch import (
    KubernetesServicePatch,
    ServicePort,
)
from ops.charm import CharmBase
from ops.main import main


class MagmaOrc8rCtracedCharm(CharmBase):
    """Creates a new instance of this object for each event."""

    def __init__(self, *args):
        """Uses the Orc8rBase library to manage events."""
        super().__init__(*args)
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[
                ServicePort(name="grpc", port=9180, targetPort=9118),
                ServicePort(name="http", port=8080, targetPort=10118),
            ],
            additional_labels={
                "app.kubernetes.io/part-of": "orc8r-app",
                "orc8r.io/obsidian_handlers": "true",
                "orc8r.io/swagger_spec": "true",
            },
            additional_annotations={
                "orc8r.io/obsidian_handlers_path_prefixes": "/magma/v1/networks/:network_id/tracing,"  # noqa: E501
            },
        )
        startup_command = (
            "/usr/bin/envdir "
            "/var/opt/magma/envdir "
            "/var/opt/magma/bin/ctraced "
            "-run_echo_server=true "
            "-logtostderr=true -v=0"
        )
        self._orc8r_base = Orc8rBase(self, startup_command=startup_command)


if __name__ == "__main__":
    main(MagmaOrc8rCtracedCharm)
