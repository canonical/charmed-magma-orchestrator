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
orc8r-ha
orc8r-lte
orc8r-metricsd
orc8r-nginx
orc8r-obsidian
orc8r-orchestrator
orc8r-policydb
orc8r-service-registry
orc8r-smsd
orc8r-state
orc8r-streamer
orc8r-subscriberdb
orc8r-subscriberdb-cache
orc8r-tenants
"


for charm in ${charms}; do
    build ${charm}
done

wait
