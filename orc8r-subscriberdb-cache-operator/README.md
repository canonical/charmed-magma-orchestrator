# magma-orc8r-subscriberdb-cache

## Description
magma-orc8r-subscriberdb-cache is a cache for the subscriberdb service.

## Usage

```bash
juju deploy postgresql-k8s
juju deploy magma-orc8r-subscriberdb-cache orc8r-subscriberdb-cache
juju relate orc8r-subscriberdb-cache postgresql-k8s:db
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

## Relations

The magma-orc8r-subscriberdb-cache service relies on a relation to a Database.

The current setup has only been tested with relation to the `postgresql-k8s` charm.

## OCI Images

Default: linuxfoundation.jfrog.io/magma-docker/controller:1.8.0

