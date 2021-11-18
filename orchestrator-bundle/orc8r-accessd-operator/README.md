# orc8r-accessd

## Description
orc8r-accessd stores, manages and verifies operator identity objects and their rights to access 
(read/write) entities. magma-orc8r-accessd is one of the building blocks of magma orchestrator 
service.

## Usage

```bash
juju deploy postgresql-k8s
juju deploy ./magma-orc8r-accessd_ubuntu-20.04-amd64.charm \
    --resource magma-orc8r-accessd-image=docker.artifactory.magmacore.org/controller:1.6.0
juju relate magma-orc8r-accessd postgresql-k8s:db-admin
```

## Relations

The magma-orc8r-accessd service relies on a relation to a Database. 

The current setup has only been tested with relation to the `postgresql-k8s` charm.

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0

## Contributing

Please see `CONTRIBUTING.md` for developer guidance.
