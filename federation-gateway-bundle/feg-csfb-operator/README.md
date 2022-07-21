# feg-csfb

## Description

Federation Gateway csfb service translates calls from GRPC interface to csfb protocol between AGW and VLR.

## Usage

Deploy using Juju:

```bash
juju deploy magma-feg-csfb feg-csfb --trust
```

## OCI Images

Default: docker.artifactory.magmacore.org/gateway_go:1.6.0
