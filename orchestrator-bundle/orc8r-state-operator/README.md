# magma-orc8r-state

## Description
magma-orc8r-state maintains reported state from devices in the network.

## Usage

```bash
juju deploy postgresql-k8s
juju deploy ./magma-orc8r-state_ubuntu-20.04-amd64.charm \
  --resource magma-orc8r-state-image=docker.artifactory.magmacore.org/controller:1.6.0
juju relate magma-orc8r-state postgresql-k8s:db
```

## Relations

The magma-orc8r-state service relies on a relation to a Database. 

The current setup has only been tested with relation to the `postgresql-k8s` charm.

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0

## Contributing

Please see `CONTRIBUTING.md` for developer guidance.
