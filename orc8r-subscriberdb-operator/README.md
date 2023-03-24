# magma-orc8r-subscriberdb

## Description
magma-orc8r-subscriberdb manages subscribers via a northbound CRUD API and a southbound subscriber stream.

## Usage

```bash
juju deploy postgresql-k8s
juju deploy magma-orc8r-subscriberdb orc8r-subscriberdb
juju relate orc8r-subscriberdb postgresql-k8s:db
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

## Relations

The magma-orc8r-subscriberdb service relies on a relation to a Database.

The current setup has only been tested with relation to the `postgresql-k8s` charm.

## OCI Images

Default: linuxfoundation.jfrog.io/magma-docker/controller:1.8.0

