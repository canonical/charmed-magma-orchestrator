#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

from kubernetes import kubernetes
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus

from kubernetes_service import K8sServicePatch

logger = logging.getLogger(__name__)


class FluentdElasticsearchCharm(CharmBase):

    _stored = StoredState()

    def __init__(self, *args):
        """
        An instance of this object everytime an event occurs
        """
        super().__init__(*args)
        self.framework.observe(
            self.on.fluentd_elasticsearch_pebble_ready, self._on_fluentd_elasticsearch_pebble_ready
        )
        self.framework.observe(self.on.install, self._on_install)
        self._stored.set_default(
            _k8s_authed=False,
        )

    def _on_fluentd_elasticsearch_pebble_ready(self, event):
        """
        Runs whenever the charm is ready
        """
        container = event.workload
        pebble_layer = {
            "summary": "fluentd_elasticsearch layer",
            "description": "pebble config layer for fluentd_elasticsearch",
            "services": {
                "fluentd_elasticsearch": {
                    "override": "replace",
                    "summary": "fluentd_elasticsearch",
                    "startup": "enabled",
                    "command": "./run.sh",
                    "environment": {
                        "OUTPUT_HOST": "bla.com",  # TODO Change to elasticsearch cluster host (TELCO-58)  # noqa: E501
                        "OUTPUT_PORT": 443,
                        "OUTPUT_SCHEME": "https",
                        "OUTPUT_SSL_VERSION": "TLSv1",
                        "OUTPUT_BUFFER_CHUNK_LIMIT": "2M",
                        "OUTPUT_BUFFER_QUEUE_LIMIT": 8,
                    },
                }
            },
        }
        container.add_layer("fluentd_elasticsearch", pebble_layer, combine=True)
        container.autostart()
        self.unit.status = ActiveStatus()

    def _on_install(self, event):
        """
        Runs each time the charm is installed
        """
        self._k8s_auth()
        K8sServicePatch.set_ports(
            self.app.name,
            [
                ("fluentd", 24224, 24224, "TCP"),
            ],
        )

    def _k8s_auth(self):
        """
        Authenticate to kubernetes
        """
        if self._stored._k8s_authed:
            return
        kubernetes.config.load_incluster_config()
        self._stored._k8s_authed = True


if __name__ == "__main__":
    main(FluentdElasticsearchCharm)
