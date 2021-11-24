# magma-orc8r-streamer

## Description
magma-orc8r-streamer fetches updates for various data streams (e.g. mconfig, subscribers, etc.) from the appropriate Orchestrator service, returning these to the gateways.


## Usage

```bash
juju deploy ./magma-orc8r-streamer_ubuntu-20.04-amd64.charm \
  --resource magma-orc8r-streamer-image=docker.artifactory.magmacore.org/controller:1.6.0 \
  orc8r-streamer
```

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0

## Contributing

Please see `CONTRIBUTING.md` for developer guidance.
