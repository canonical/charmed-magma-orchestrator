# magma-orc8r-analytics

## Description
analytics periodically fetches and aggregates metrics for all deployed Orchestrator modules, 
exporting the aggregations to Prometheus.

## Usage

```bash
juju deploy ./magma-orc8r-analytics_ubuntu-20.04-amd64.charm \
  --resource magma-orc8r-analytics-image=docker.artifactory.magmacore.org/controller:1.6.0
```

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0

## Contributing

Please see `CONTRIBUTING.md` for developer guidance.
