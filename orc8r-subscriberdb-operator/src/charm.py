#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Manages subscribers via a northbound CRUD API and a southbound subscriber stream."""

from charms.magma_orc8r_libs.v0.orc8r_base_db import Orc8rBase
from charms.observability_libs.v1.kubernetes_service_patch import (
    KubernetesServicePatch,
    ServicePort,
)
from ops.charm import CharmBase
from ops.main import main


class MagmaOrc8rSubscriberdbCharm(CharmBase):
    """An instance of this object everytime an event occurs."""

    def __init__(self, *args):
        """Uses the Orc8rBase library to manage events."""
        super().__init__(*args)
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[
                ServicePort(name="grpc", port=9180, targetPort=9083),
                ServicePort(name="http", port=8080, targetPort=10083),
                ServicePort(name="grpc-internal", port=9190, targetPort=9183),
            ],
            additional_labels={
                "app.kubernetes.io/part-of": "orc8r-app",
                "orc8r.io/obsidian_handlers": "true",
                "orc8r.io/state_indexer": "true",
                "orc8r.io/swagger_spec": "true",
            },
            additional_annotations={
                "orc8r.io/state_indexer_types": "mobilityd_ipdesc_record",
                "orc8r.io/state_indexer_version": "1",
                "orc8r.io/obsidian_handlers_path_prefixes": "/magma/v1/lte/:network_id/msisdns, "
                "/magma/v1/lte/:network_id/subscriber_state, "
                "/magma/v1/lte/:network_id/subscribers, "
                "/magma/v1/lte/:network_id/subscribers_v2,",
            },
        )
        startup_command = (
            "/usr/bin/envdir "
            "/var/opt/magma/envdir "
            "/var/opt/magma/bin/subscriberdb "
            "-run_echo_server=true "
            "-logtostderr=true "
            "-v=0"
        )
        self._orc8r_base = Orc8rBase(self, startup_command=startup_command)


if __name__ == "__main__":
    main(MagmaOrc8rSubscriberdbCharm)
