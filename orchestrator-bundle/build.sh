#!/bin/bash

set -euo pipefail

function build_magma_charm() {
  charm="$1"
    pushd "${charm}-operator/"
    charmcraft pack
    mv "magma-${charm}_ubuntu-20.04-amd64.charm" "${charm}.charm"
    popd
}


function build_generic_charm() {
  charm="$1"
    pushd "${charm}-operator/"
    charmcraft pack
    mv "${charm}_ubuntu-20.04-amd64.charm" "${charm}.charm"
    popd
}

#orc8r-analytics
#orc8r-bootstrapper
#orc8r-certifier
#orc8r-configurator
#orc8r-ctraced
#orc8r-device
#orc8r-directoryd
#orc8r-dispatcher
#orc8r-eventd
#orc8r-ha
#orc8r-lte
#orc8r-metricsd
#orc8r-nginx
#orc8r-obsidian
#orc8r-orchestrator
#orc8r-policydb
#orc8r-service-registry
#orc8r-smsd
#orc8r-state
#orc8r-streamer
#orc8r-subscriberdb
#orc8r-subscriberdb-cache
#orc8r-tenants
#"

magma_charms="
orc8r-accessd
nms-magmalte
nms-nginx-proxy
"


for magma_charm in $magma_charms; do
    build_magma_charm $magma_charm &
done

build_generic_charm "fluentd-elasticsearch" &

wait
