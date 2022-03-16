#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import base64
import unittest
from unittest.mock import MagicMock, Mock, PropertyMock, patch

from lightkube.models.apps_v1 import StatefulSetSpec
from lightkube.models.core_v1 import Container, PodSpec, PodTemplateSpec
from lightkube.models.meta_v1 import LabelSelector
from lightkube.resources.apps_v1 import StatefulSet
from ops.testing import Harness

from charm import MagmaOrc8rMetricsdCharm


class MockModel:
    def __init__(self, name: str):
        self._name = name

    @property
    def name(self):
        return self._name


class TestCharm(unittest.TestCase):
    @patch(
        "charm.KubernetesServicePatch",
        lambda charm, ports, additional_labels, additional_annotations: None,
    )
    def setUp(self):
        self.harness = Harness(MagmaOrc8rMetricsdCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
        self.maxDiff = None

    @patch("lightkube.core.client.GenericSyncClient", MagicMock)
    @patch("lightkube.Client.create")
    @patch("charm.MagmaOrc8rMetricsdCharm.model", new_callable=PropertyMock)
    def test_given_new_charm_when_on_install_event_then_secret_is_created(
        self, patch_model, patch_create
    ):
        event = Mock()
        namespace = "whatever namespace"
        patch_model.return_value = MockModel(namespace)

        self.harness.charm._on_install(event)

        args, kwargs = patch_create.call_args
        expected_secret_data = {
            "metricsd.yml": base64.b64encode(open("src/metricsd.yml", "rb").read()).decode("utf-8")
        }
        secret = args[0]
        assert secret.data == expected_secret_data
        assert secret.metadata.name == "metricsd-config"
        assert secret.metadata.namespace == namespace

    @patch("lightkube.core.client.GenericSyncClient", Mock)
    @patch("lightkube.Client.patch")
    @patch("lightkube.Client.get")
    @patch("charm.MagmaOrc8rMetricsdCharm.model", new_callable=PropertyMock)
    def test_given_new_charm_when_on_install_event_then_volume_is_added_to_statefulset(
        self, patch_model, patch_get, patch_patch
    ):
        event = Mock()
        namespace = "whatever namespace"
        patch_get.return_value = StatefulSet(
            spec=StatefulSetSpec(
                serviceName="whatever",
                selector=LabelSelector(),
                template=PodTemplateSpec(
                    spec=PodSpec(
                        containers=[
                            Container(name="charm"),
                            Container(name="workload", volumeMounts=[]),
                        ],
                        volumes=[],
                    )
                ),
            )
        )
        patch_model.return_value = MockModel(namespace)

        self.harness.charm._on_install(event)

        args, kwargs = patch_patch.call_args
        statefulset = kwargs["obj"]
        volumes = statefulset.spec.template.spec.volumes
        assert len(volumes) == 1
        assert volumes[0].name == "metricsd-config-volume"
        assert volumes[0].secret.secretName == "metricsd-config"

    @patch("lightkube.core.client.GenericSyncClient", Mock)
    @patch("lightkube.Client.patch")
    @patch("lightkube.Client.get")
    @patch("charm.MagmaOrc8rMetricsdCharm.model", new_callable=PropertyMock)
    def test_given_new_charm_when_on_install_event_then_volume_is_mounted(
        self, patch_model, patch_get, patch_patch
    ):
        event = Mock()
        namespace = "whatever namespace"
        patch_get.return_value = StatefulSet(
            spec=StatefulSetSpec(
                serviceName="whatever",
                selector=LabelSelector(),
                template=PodTemplateSpec(
                    spec=PodSpec(
                        containers=[
                            Container(name="charm"),
                            Container(name="workload", volumeMounts=[]),
                        ],
                        volumes=[],
                    )
                ),
            )
        )
        patch_model.return_value = MockModel(namespace)

        self.harness.charm._on_install(event)

        args, kwargs = patch_patch.call_args
        statefulset = kwargs["obj"]
        volume_mounts = statefulset.spec.template.spec.containers[1].volumeMounts
        assert len(volume_mounts) == 1
        assert volume_mounts[0].name == "metricsd-config-volume"
