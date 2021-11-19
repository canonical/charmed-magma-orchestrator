# orc8r-ctraced

## Description
magma-orc8r-ctraced handles gateway call traces, exposing this functionality via a CRUD API.

## Usage

```bash
juju deploy postgresql-k8s
juju deploy ./magma-orc8r-ctraced_ubuntu-20.04-amd64.charm \
  --resource magma-orc8r-ctraced-image=docker.artifactory.magmacore.org/controller:1.6.0
juju relate magma-orc8r-ctraced postgresql-k8s:db
```

## Relations

The magma-orc8r-ctraced service relies on a relation to a Database. 

The current setup has only been tested with relation to the `postgresql-k8s` charm.

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0

## Contributing

Please see `CONTRIBUTING.md` for developer guidance.
