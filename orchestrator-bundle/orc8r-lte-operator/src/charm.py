#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

from charms.magma_orc8r_libs.v0.orc8r_base_db import Orc8rBase
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from ops.charm import CharmBase
from ops.main import main


class MagmaOrc8rLteCharm(CharmBase):
    def __init__(self, *args):
        """Creates a new instance of this object for each event."""
        super().__init__(*args)
        self._service_patcher = KubernetesServicePatch(
            charm=self,
            ports=[("grpc", 9180, 9113), ("http", 8080, 10113)],
            additional_labels={
                "app.kubernetes.io/part-of": "orc8r-app",
                "orc8r.io/analytics_collector": "true",
                "orc8r.io/mconfig_builder": "true",
                "orc8r.io/obsidian_handlers": "true",
                "orc8r.io/state_indexer": "true",
                "orc8r.io/stream_provider": "true",
                "orc8r.io/swagger_spec": "true",
            },
            additional_annotations={
                "orc8r.io/state_indexer_types": "single_enodeb",
                "orc8r.io/state_indexer_version": "1",
                "orc8r.io/obsidian_handlers_path_prefixes": "/magma/v1/lte, "
                "/magma/v1/lte/:network_id,",
                "orc8r.io/stream_provider_streams": "apn_rule_mappings, "
                "base_names, "
                "network_wide_rules, "
                "policydb, "
                "rating_groups, "
                "subscriberdb,",
            },
        )
        startup_command = (
            "/usr/bin/envdir "
            "/var/opt/magma/envdir "
            "/var/opt/magma/bin/lte "
            "-run_echo_server=true "
            "-logtostderr=true "
            "-v=0"
        )
        self._orc8r_base = Orc8rBase(self, startup_command=startup_command)


if __name__ == "__main__":
    main(MagmaOrc8rLteCharm)
