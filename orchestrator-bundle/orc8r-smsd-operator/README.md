# magma-orc8r-smsd

## Description
magma-orc8r-smsd provides CRUD support for SMS messages to be fetched by LTE gateways.

## Usage

```bash
juju deploy postgresql-k8s
juju deploy ./magma-orc8r-smsd_ubuntu-20.04-amd64.charm \
  --resource magma-orc8r-smsd-image=docker.artifactory.magmacore.org/controller:1.6.0 \
  orc8r-smsd
juju relate orc8r-smsd postgresql-k8s:db
```

## Relations

The magma-orc8r-smsd service relies on a relation to a Database. 

The current setup has only been tested with relation to the `postgresql-k8s` charm.

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0

## Contributing

Please see `CONTRIBUTING.md` for developer guidance.
