# magma-orc8r-orchestrator

## Description
- Mconfigs for configuration of core gateway service configurations (e.g. magmad, eventd, state)
- Metrics exporting to Prometheus
- CRUD API for core Orchestrator network entities (networks, gateways, upgrade tiers, events, etc.)

## Usage

```bash
juju deploy ./magma-orc8r-orchestrator_ubuntu-20.04-amd64.charm \
  --resource magma-orc8r-orchestrator-image=docker.artifactory.magmacore.org/controller:1.6.0 \
  orc8r-orchestrator
```

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0

## Contributing

Please see `CONTRIBUTING.md` for developer guidance.
