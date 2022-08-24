# feg-control-proxy

## Description

Federation Gateway control proxy service.

## Usage

Deploy using Juju:

```bash
juju deploy magma-feg-control-proxy feg-control-proxy
```

Provide required certificates through config file.
```bash
juju config feg-control-proxy --file <config file>
```
**NOTE**: If you want to try it out with dummy certs for the sake of testing,
you can use the `certs-config.yaml` file provided.

## OCI Images

Default: docker.artifactory.magmacore.org/gateway_python:1.6.0
