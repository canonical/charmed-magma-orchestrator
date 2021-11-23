# magma-orc8r-tenants

## Description
magma-orc8r-tenants provides CRUD interface for managing NMS tenants.

## Usage

```bash
juju deploy postgresql-k8s
juju deploy ./magma-orc8r-tenants_ubuntu-20.04-amd64.charm \
  --resource magma-orc8r-tenants-image=docker.artifactory.magmacore.org/controller:1.6.0
juju relate magma-orc8r-tenants postgresql-k8s:db
```

## Relations

The magma-orc8r-tenants service relies on a relation to a Database. 

The current setup has only been tested with relation to the `postgresql-k8s` charm.

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0

## Contributing

Please see `CONTRIBUTING.md` for developer guidance.
