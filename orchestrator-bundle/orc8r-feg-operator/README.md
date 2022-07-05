# magma-orc8r-feg

## Description

Feg provides Mconfigs for configuration of FeG-related gateway service configurations 
(e.g. s6a_proxy, session_proxy) and CRUD API for LTE network entities 
(FeG networks, federated gateways, etc.)

## Usage
Deploy using Juju:

```bash
juju deploy magma-orc8r-feg  orc8r-feg --trust
```

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0
