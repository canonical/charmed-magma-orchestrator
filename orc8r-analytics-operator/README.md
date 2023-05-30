# magma-orc8r-analytics

## Description
magma-orc8r-analytics periodically fetches and aggregates metrics for all deployed Orchestrator modules, 
exporting the aggregations to Prometheus.

## Usage

```bash
juju deploy magma-orc8r-analytics orc8r-analytics
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

## OCI Images

Default: ghcr.io/canonical/magma-orc8r-controller:1.8.0


