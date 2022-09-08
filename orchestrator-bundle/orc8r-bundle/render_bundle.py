#!/usr/bin/env python3

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
        type=Path,
        help="channel for the charms in the bundle",
        required= True
    )
    bundle_args, _= parser.parse_known_args()

    return bundle_args.template, bundle_args.output, bundle_args.channel

if __name__ == "__main__":
    template, output, channel = parse_args()
    env = jinja2.Environment(loader=jinja2.FileSystemLoader("./"))
    t = env.get_template(template)
    with open(template) as t:
        jinja_template = jinja2.Template(t.read(), autoescape=True)
    with open(output, 'wt') as o:
        jinja_template.stream(channel=channel).dump(o)