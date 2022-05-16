# orc8r-accessd

## Description
magma-orc8r-accessd stores, manages and verifies operator identity objects and their rights to access 
(read/write) entities. magma-orc8r-accessd is one of the building blocks of magma orchestrator 
service.

## Usage

```bash
juju deploy postgresql-k8s
juju deploy magma-orc8r-accessd orc8r-accessd
juju relate orc8r-accessd postgresql-k8s:db
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

## Relations

The magma-orc8r-accessd service relies on a relation to a Database. 

The current setup has only been tested with relation to the `postgresql-k8s` charm.

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.7.0
