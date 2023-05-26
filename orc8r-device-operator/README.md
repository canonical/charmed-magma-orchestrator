# magma-orc8r-device

## Description
magma-orc8r-device maintains configurations and metadata for devices in the network (e.g. gateways)

## Usage

```bash
juju deploy postgresql-k8s
juju deploy magma-orc8r-device orc8r-device
juju relate orc8r-device postgresql-k8s:db
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

## Relations

The magma-orc8r-device service relies on a relation to a Database. 

The current setup has only been tested with relation to the `postgresql-k8s` charm.

## OCI Images

Default: ghcr.io/canonical/magma-orc8r-controller:1.8.0


