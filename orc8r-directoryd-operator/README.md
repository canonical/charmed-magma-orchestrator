# magma-orc8r-directoryd

## Description

magma-orc8r-directoryd stores subscriber identity (e.g. IMSI, IP address, MAC address) and location (gateway hardware ID).

## Usage

```bash
juju deploy postgresql-k8s
juju deploy magma-orc8r-directoryd orc8r-directoryd
juju relate orc8r-directoryd postgresql-k8s:database
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

## Relations

The magma-orc8r-directoryd service relies on a relation to a Database.

The current setup has only been tested with relation to the `postgresql-k8s` charm.

## OCI Images

Default: ghcr.io/canonical/magma-orc8r-controller:1.8.0
