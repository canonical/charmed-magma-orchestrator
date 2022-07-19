#!/bin/bash

set -euo pipefail

function build() {
  charm="$1"
    pushd "federation-gateway-bundle/${charm}-operator/"
    charmcraft pack
    mv -f "magma-${charm}_ubuntu-20.04-amd64.charm" "${charm}.charm"
    popd
}

charms="
feg-eap-sim
feg-health
feg-hello
feg-radiusd
feg-s8-proxy
feg-session-proxy
"

for charm in ${charms}; do
    build ${charm}
done

wait
