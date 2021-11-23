# magma-orc8r-metricsd

## Description
magma-orc8r-metricsd collects runtime metrics from gateways and Orchestrator services

## Usage

```bash
juju deploy ./magma-orc8r-metricsd_ubuntu-20.04-amd64.charm \
  --resource magma-orc8r-metricsd-image=docker.artifactory.magmacore.org/controller:1.6.0 \
  orc8r-metricsd
```

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0

## Contributing

Please see `CONTRIBUTING.md` for developer guidance.
