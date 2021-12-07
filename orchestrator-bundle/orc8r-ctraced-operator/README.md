# magma-orc8r-ctraced

## Description
magma-orc8r-ctraced handles gateway call traces, exposing this functionality via a CRUD API.

## Usage

```bash
juju deploy postgresql-k8s
juju deploy magma-orc8r-ctraced orc8r-ctraced
juju relate orc8r-ctraced postgresql-k8s:db
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

## Relations

The magma-orc8r-ctraced service relies on a relation to a Database. 

The current setup has only been tested with relation to the `postgresql-k8s` charm.

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0
