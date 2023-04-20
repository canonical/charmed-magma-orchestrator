# magma-orc8r-lte

## Description
magma-orc8r-lte provides
- Mconfigs for configuration of LTE-related gateway service configurations (e.g. mme, pipelined, policydb)
- CRUD API for LTE network entities (LTE networks, LTE gateways, eNodeBs, etc.)

## Usage

```bash
juju deploy postgresql-k8s
juju deploy magma-orc8r-lte orc8r-lte
juju relate orc8r-lte postgresql-k8s:db
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

## Relations

The magma-orc8r-lte service relies on a relation to a Database. 

The current setup has only been tested with relation to the `postgresql-k8s` charm.

## OCI Images

Default: linuxfoundation.jfrog.io/magma-docker/controller:1.6.0

