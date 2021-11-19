# orc8r-device

## Description
device maintains configurations and metadata for devices in the network (e.g. gateways)

## Usage

```bash
juju deploy postgresql-k8s
juju deploy ./magma-orc8r-device_ubuntu-20.04-amd64.charm \
  --resource magma-orc8r-device-image=docker.artifactory.magmacore.org/controller:1.6.0
juju relate magma-orc8r-device postgresql-k8s:db
```

## Relations

The magma-orc8r-device service relies on a relation to a Database. 

The current setup has only been tested with relation to the `postgresql-k8s` charm.

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0

## Contributing

Please see `CONTRIBUTING.md` for developer guidance.
