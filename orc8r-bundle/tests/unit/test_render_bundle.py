# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest

from render_bundle import render_bundle


def test_given_channel_is_not_provided_and_local_not_set_when_render_bundle_then_valueerror_is_raised():  # noqa: E501
    with pytest.raises(ValueError) as e:
        render_bundle(
            template="bundle.yaml.j2",
            output="tests/unit/rendered_bundle_charmhub_edge.yaml",
        )

    assert "Either channel must be specified or local set to True" == str(e.value)


def test_given_channel_is_provided_and_local_set_to_true_when_render_bundle_then_valueerror_is_raised():  # noqa: E501
    with pytest.raises(ValueError) as e:
        render_bundle(
            channel="edge",
            local=True,
            template="bundle.yaml.j2",
            output="tests/unit/rendered_bundle_charmhub_edge.yaml",
        )

    assert "If local is true, channel must not be set" == str(e.value)


def test_given_channel_is_edge_when_render_bundle_then_bundle_is_rendered_correctly():
    render_bundle(
        channel="edge",
        template="bundle.yaml.j2",
        output="tests/unit/rendered_bundle_charmhub_edge.yaml",
    )

    with open("tests/unit/rendered_bundle_charmhub_edge.yaml") as rendered_bundle_file:
        rendered_bundle = rendered_bundle_file.read()

    with open("tests/unit/expected_bundles/charmhub_edge.yaml") as expected_bundle_file:
        expected_bundle = expected_bundle_file.read()

    assert rendered_bundle == expected_bundle


def test_given_local_charms_when_render_bundle_then_bundle_is_rendered_correctly():
    render_bundle(
        template="bundle.yaml.j2",
        local=True,
        output="tests/unit/rendered_bundle_local.yaml",
    )

    with open("tests/unit/rendered_bundle_local.yaml") as rendered_bundle_file:
        rendered_bundle = rendered_bundle_file.read()

    with open("tests/unit/expected_bundles/local.yaml") as expected_bundle_file:
        expected_bundle = expected_bundle_file.read()

    assert rendered_bundle == expected_bundle
