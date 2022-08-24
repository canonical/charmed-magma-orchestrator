# magma-feg-session-proxy

## Description

Federation Gateway session-proxy service translates calls from GRPC to gx/gy protocol between AGW and PCRF/OCS.

## Usage

Deploy using Juju:

```bash
juju deploy magma-feg-session-proxy feg-session-proxy
```

## OCI Images

Default: docker.artifactory.magmacore.org/gateway_go:1.6.0
