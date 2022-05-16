# magma-orc8r-configurator

## Description
magma-orc8r-configurator maintains configurations and metadata for networks and network entity
structures

## Usage

```bash
juju deploy postgresql-k8s
juju deploy magma-orc8r-configurator orc8r-configurator
juju relate orc8r-configurator postgresql-k8s:db
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

## Relations

The magma-orc8r-configurator service relies on a relation to a Database. 

The current setup has only been tested with relation to the `postgresql-k8s` charm.

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.7.0
