# magma-orc8r-subscriberdb-cache

## Description
magma-orc8r-subscriberdb-cache is a cache for the subscriberdb service.

## Usage

```bash
juju deploy postgresql-k8s
juju deploy ./magma-orc8r-subscriberdb-cache_ubuntu-20.04-amd64.charm \
  --resource magma-orc8r-subscriberdb-cache-image=docker.artifactory.magmacore.org/controller:1.6.0 \
  orc8r-subscriberdb-cache
juju relate orc8r-subscriberdb-cache postgresql-k8s:db
```

## Relations

The magma-orc8r-subscriberdb-cache service relies on a relation to a Database. 

The current setup has only been tested with relation to the `postgresql-k8s` charm.

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0

## Contributing

Please see `CONTRIBUTING.md` for developer guidance.
