# magma-orc8r-feg

## Description

Feg provides Mconfigs for configuration of FeG-related gateway service configurations 
(e.g. s6a_proxy, session_proxy) and CRUD API for LTE network entities 
(FeG networks, federated gateways, etc.)

## Usage
**magma-orc8r-feg** can be deployed via Juju command line using below commands:

```bash
juju deploy magma-orc8r-feg  orc8r-feg --trust
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

Before running **juju deploy** command, make sure charm has been built using:
```bash
charmcraft pack
```

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0
