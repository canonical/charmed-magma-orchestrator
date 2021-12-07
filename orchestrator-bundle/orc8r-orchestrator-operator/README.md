# magma-orc8r-orchestrator

## Description
magma-orc8r-orchestrator provides:
- Mconfigs for configuration of core gateway service configurations (e.g. magmad, eventd, state)
- Metrics exporting to Prometheus
- CRUD API for core Orchestrator network entities (networks, gateways, upgrade tiers, events, etc.)

## Usage

```bash
juju deploy magma-orc8r-orchestrator orc8r-orchestrator
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0
