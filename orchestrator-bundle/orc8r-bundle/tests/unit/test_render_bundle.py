# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

from render_bundle import render_bundle


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
        local_dir="./",
        output="tests/unit/rendered_bundle_local.yaml",
    )

    with open("tests/unit/rendered_bundle_local.yaml") as rendered_bundle_file:
        rendered_bundle = rendered_bundle_file.read()

    with open("tests/unit/expected_bundles/local.yaml") as expected_bundle_file:
        expected_bundle = expected_bundle_file.read()

    assert rendered_bundle == expected_bundle
