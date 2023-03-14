# magma-orc8r-streamer

## Description
magma-orc8r-streamer fetches updates for various data streams (e.g. mconfig, subscribers, etc.) from the appropriate Orchestrator service, returning these to the gateways.


## Usage

```bash
juju deploy magma-orc8r-streamer orc8r-streamer
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

## OCI Images

Default: ghcr.io/canonical/magma-orc8r-controller:1.8.0
