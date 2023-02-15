#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""This script renders the jinja template given to it.

This scripts takes a jinja template of the magma-orc8r bundle,
and renders the bundle into an output file after adding the value of the channel.
Channel must be passed using the --channel option to this script.
Example:
```shell
./render_bundle --template bundle.yaml.j2 --output bundle.yaml --channel beta
```
"""
import argparse
from typing import Tuple

import jinja2

BUNDLE_TEMPLATE_NAME = "bundle.yaml.j2"


def parse_args() -> Tuple[str, str, bool, str]:
    parser = argparse.ArgumentParser(description="Render jinja2 bundle template from cli args.")
    parser.add_argument(
        "--template",
        type=str,
        help="bundle template to render",
        default=BUNDLE_TEMPLATE_NAME,
    )
    parser.add_argument(
        "--output", type=str, help="path to the rendered bundle yaml", required=True
    )
    parser.add_argument(
        "--local",
        type=bool,
        help="Use local path for charms (instead of charmhub)",
        required=False,
        default=False,
    )
    parser.add_argument(
        "--channel",
        type=str,
        help="channel for the charms in the bundle",
        choices=["edge", "beta", "candidate", "stable"],
        required=False,
    )
    bundle_args, _ = parser.parse_known_args()

    return (
        bundle_args.template,
        bundle_args.output,
        bundle_args.local,
        bundle_args.channel,
    )


def render_bundle(
    template: str,
    output: str,
    channel: str = "",
    local: bool = False,
) -> None:
    if not channel and not local:
        raise ValueError("Either channel must be specified or local set to True")
    if local and channel:
        raise ValueError("If local is true, channel must not be set")
    with open(template) as t:
        jinja_template = jinja2.Template(t.read(), autoescape=True)
    with open(output, "wt") as o:
        jinja_template.stream(channel=channel, local=local).dump(o)


if __name__ == "__main__":
    arg_template, arg_output, arg_local, arg_channel = parse_args()
    render_bundle(
        template=arg_template,
        output=arg_output,
        local=arg_local,
        channel=arg_channel,
    )
