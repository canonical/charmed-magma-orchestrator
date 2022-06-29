#!/bin/bash

set -euo pipefail

function fetch_orc8r_base_lib() {
  charm="$1"
    pushd "${charm}-operator/"
    charmcraft fetch-lib charms.magma_orc8r_libs.v0.orc8r_base
    popd
}

function fetch_orc8r_base_db_lib() {
  charm="$1"
    pushd "${charm}-operator/"
    charmcraft fetch-lib charms.magma_orc8r_libs.v0.orc8r_base_db
    popd
}

charms_using_orc8r_base_lib="
orc8r-analytics
orc8r-base-acct-operator
orc8r-dispatcher
orc8r-eventd
orc8r-feg-operator
orc8r-feg-relay-operator
orc8r-ha
orc8r-metricsd
orc8r-obsidian
orc8r-service-registry
orc8r-streamer
"


charms_using_orc8r_base_db_lib="
orc8r-accessd
orc8r-configurator
orc8r-ctraced
orc8r-device
orc8r-directoryd
orc8r-health-operator
orc8r-lte
orc8r-policydb
orc8r-smsd
orc8r-state
orc8r-subscriberdb-cache
orc8r-subscriberdb
orc8r-tenants
"

for charm in ${charms_using_orc8r_base_lib}; do
    fetch_orc8r_base_lib ${charm}
done

for charm in ${charms_using_orc8r_base_db_lib}; do
    fetch_orc8r_base_db_lib ${charm}
done

wait
