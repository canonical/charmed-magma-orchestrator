# magma-orc8r-feg-relay

## Description

Feg relay relays requests between access gateways and federated gateways.


## Usage
**magma-orc8r-feg-relay** can be deployed via Juju command line using below commands:

```bash
juju deploy magma-orc8r-feg-relay  orc8r-feg-relay --trust
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

Before running **juju deploy** command, make sure charm has been built using:
```bash
charmcraft pack
```

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0
