#!/bin/bash

set -euo pipefail

function build() {
  charm="$1"
    pushd "${charm}-operator/"
    charmcraft pack
    mv "magma-${charm}_ubuntu-20.04-amd64.charm" "${charm}.charm"
    popd
}

charms="
nms-magmalte
nms-nginx-proxy
orc8r-accessd
orc8r-analytics
orc8r-bootstrapper
orc8r-certifier
orc8r-configurator
orc8r-ctraced
orc8r-device
orc8r-directoryd
orc8r-dispatcher
orc8r-eventd
"


for charm in $charms; do
    build $charm &
done

wait
