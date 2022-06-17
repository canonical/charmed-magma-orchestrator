#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock, patch

from httpx import HTTPStatusError, Request, Response
from lightkube.models.core_v1 import ServicePort, ServiceSpec
from lightkube.models.meta_v1 import ObjectMeta
from lightkube.resources.core_v1 import Service
from ops import testing

from charm import MagmaOrc8rFEGRelayCharm

testing.SIMULATE_CAN_CONNECT = True


class TestCharm(unittest.TestCase):
    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports, additional_labels: None,  # noqa: E501
    )
    def setUp(self) -> None:
        self.model_name = "whatever"
        self.harness = testing.Harness(MagmaOrc8rFEGRelayCharm)
        self.harness.set_model_name(name=self.model_name)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch("lightkube.core.client.Client.create")
    @patch("lightkube.core.client.Client.get")
    @patch("lightkube.core.client.GenericSyncClient")
    def test_given_service_not_yet_created_when_install_then_feg_service_is_created(
        self, _, patch_get, patch_create
    ):
        event = Mock()
        patch_get.side_effect = HTTPStatusError(
            message="whatever message",
            request=Request(method="whatever method", url="whatever url"),
            response=Response(status_code=400),
        )

        self.harness.charm._on_install(event=event)

        patch_create.assert_called_with(
            obj=Service(
                apiVersion="v1",
                kind="Service",
                metadata=ObjectMeta(
                    labels={
                        "app.kubernetes.io/component": "feg-orc8r",
                        "app.kubernetes.io/part-of": "orc8r-app",
                    },
                    name="orc8r-feg-hello",
                    namespace="whatever",
                ),
                spec=ServiceSpec(
                    ports=[
                        ServicePort(
                            port=9180,
                            name="grpc",
                        )
                    ],
                    selector={"app.kubernetes.io/component": "feg-relay"},
                    type="ClusterIP",
                ),
            )
        )

    @patch("lightkube.core.client.Client.create")
    @patch("lightkube.core.client.Client.get")
    @patch("lightkube.core.client.GenericSyncClient")
    def test_given_service_already_created_when_install_then_feg_service_is_not_created(
        self, _, patch_get, patch_create
    ):
        event = Mock()
        patch_get.return_value = Service(
            kind="Service",
            metadata=ObjectMeta(
                name="whatever name",
                namespace="whatever",
            ),
        )

        self.harness.charm._on_install(event=event)

        patch_create.assert_not_called()
