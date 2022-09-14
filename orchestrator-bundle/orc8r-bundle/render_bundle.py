#!/usr/bin/env python3

"""This script renders the jinja template given to it.

This scripts takes a jinja template of the magma-orc8r bundle,
and renders the bundle into an output file after adding the value of the channel.
Channel must be passed using the --channel option to this script.
Example:
```shell
./render_bundle --template bundle.yaml.j2 --output bundle.yaml --channel beta
```
"""
import jinja2
import argparse
from pathlib import Path
from typing import Dict, Tuple

BUNDLE_TEMPLATE_NAME = "bundle.yaml.j2"

def parse_args() -> Tuple[str, Path, str]:
    parser = argparse.ArgumentParser(description="Render jinja2 bundle template from cli args.")
    parser.add_argument(
        "--template",
        type=str,
        help="bundle template to render",
        default=BUNDLE_TEMPLATE_NAME,
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="path to the rendered bundle yaml",
        required= True
    )
    parser.add_argument(
        "--channel",
        type=str,
        help="channel for the charms in the bundle",
        choices=['edge', 'beta', 'candidate', 'stable'],
        required= True
    )
    bundle_args, _= parser.parse_known_args()

    return bundle_args.template, bundle_args.output, bundle_args.channel

if __name__ == "__main__":
    template, output, channel = parse_args()
    env = jinja2.Environment(loader=jinja2.FileSystemLoader("./"))
    with open(template) as t:
        jinja_template = jinja2.Template(t.read(), autoescape=True)
    with open(output, 'wt') as o:
        jinja_template.stream(channel=channel).dump(o)
