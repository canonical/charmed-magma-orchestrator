# orc8r-dispatcher

## Description
magma-orc8r-dispatcher maintains SyncRPC connections (HTTP2 bidirectional streams) with gateways.

## Usage

```bash
juju deploy ./magma-orc8r-dispatcher_ubuntu-20.04-amd64.charm \
  --resource magma-orc8r-dispatcher-image=docker.artifactory.magmacore.org/controller:1.6.0
```

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0

## Contributing

Please see `CONTRIBUTING.md` for developer guidance.
