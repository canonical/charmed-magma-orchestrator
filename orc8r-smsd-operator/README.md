# magma-orc8r-smsd

## Description
magma-orc8r-smsd provides CRUD support for SMS messages to be fetched by LTE gateways.

## Usage

```bash
juju deploy postgresql-k8s
juju deploy magma-orc8r-smsd orc8r-smsd
juju relate orc8r-smsd postgresql-k8s:db
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

## Relations

The magma-orc8r-smsd service relies on a relation to a Database. 

The current setup has only been tested with relation to the `postgresql-k8s` charm.

## OCI Images

Default: ghcr.io/canonical/magma-lte-controller:1.8.0

