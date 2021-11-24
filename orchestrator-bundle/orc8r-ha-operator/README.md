# magma-orc8r-ha

## Description
ha provides interface for secondary gateways in an HA deployment to find offload status for UEs

## Usage

```bash
juju deploy ./magma-orc8r-ha_ubuntu-20.04-amd64.charm \
  --resource magma-orc8r-ha-image=docker.artifactory.magmacore.org/controller:1.6.0 \
  orc8r-ha
```

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0

## Contributing

Please see `CONTRIBUTING.md` for developer guidance.
