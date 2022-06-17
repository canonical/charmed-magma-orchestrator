#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.


import logging

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus
from ops.pebble import Layer


logger = logging.getLogger(__name__)


class AgwcConfigCharm(CharmBase):

    def __init__(self, *args):
        super().__init__(*args)
        self._container_name = self._service_name = "magma-agwc-config"
        self._container = self.unit.get_container(self._container_name)
        self.framework.observe(self.on.magma_agwc_config_pebble_ready, self._on_magma_agwc_config_pebble_ready)

    def _on_magma_agwc_config_pebble_ready(self, event):

        # Get a reference the container attribute on the PebbleReadyEvent
        container = event.workload
        # Define an initial Pebble layer configuration
        pebble_layer = self._pebble_layer
        # Add initial Pebble config layer using the Pebble API
        container.add_layer("agwc_config", pebble_layer, combine=True)
        # Autostart any services that were defined with startup: enabled
        container.autostart()
        # Learn more about statuses in the SDK docs:
        # https://juju.is/docs/sdk/constructs#heading--statuses
        self.unit.status = ActiveStatus()

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
                                   "/var/opt/magma/bin/certifier "
                                   f"-cac={self.BASE_CERTS_PATH}/certifier.pem "
                                   f"-cak={self.BASE_CERTS_PATH}/certifier.key "
                                   f"-vpnc={self.BASE_CERTS_PATH}/vpn_ca.crt "
                                   f"-vpnk={self.BASE_CERTS_PATH}/vpn_ca.key "
                                   "-logtostderr=true "
                                   "-v=0",
                        "environment": {
                            "DATABASE_SOURCE": f"dbname={self.DB_NAME} "
                                               f"user={self._get_db_connection_string.user} "
                                               f"password={self._get_db_connection_string.password} "
                                               f"host={self._get_db_connection_string.host} "
                                               f"sslmode=disable",
                            "SQL_DRIVER": "postgres",
                            "SQL_DIALECT": "psql",
                            "SERVICE_HOSTNAME": "magma-orc8r-certifier",
                            "SERVICE_REGISTRY_MODE": "k8s",
                            "SERVICE_REGISTRY_NAMESPACE": self._namespace,
                        },
                    }
                },
            }
        )

if __name__ == "__main__":
    main(AgwcConfigCharm)
