# orc8r-lte

## Description
magma-orc8r-lte provides
- Mconfigs for configuration of LTE-related gateway service configurations (e.g. mme, pipelined, policydb)
- CRUD API for LTE network entities (LTE networks, LTE gateways, eNodeBs, etc.)

## Usage

```bash
juju deploy postgresql-k8s
juju deploy ./magma-orc8r-lte_ubuntu-20.04-amd64.charm \
  --resource magma-orc8r-lte-image=docker.artifactory.magmacore.org/controller:1.6.0
juju relate magma-orc8r-lte postgresql-k8s:db
```

## Relations

The magma-orc8r-lte service relies on a relation to a Database. 

The current setup has only been tested with relation to the `postgresql-k8s` charm.

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0

## Contributing

Please see `CONTRIBUTING.md` for developer guidance.
