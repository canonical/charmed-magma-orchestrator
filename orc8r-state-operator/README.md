# magma-orc8r-state

## Description
magma-orc8r-state maintains reported state from devices in the network.

## Usage

```bash
juju deploy postgresql-k8s
juju deploy magma-orc8r-state orc8r-state
juju relate orc8r-state postgresql-k8s:db
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

## Relations

The magma-orc8r-state service relies on a relation to a Database. 

The current setup has only been tested with relation to the `postgresql-k8s` charm.

## OCI Images

Default: linuxfoundation.jfrog.io/magma-docker/controller:1.6.0

