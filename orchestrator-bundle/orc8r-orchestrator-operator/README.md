# magma-orc8r-orchestrator

## Description

magma-orc8r-orchestrator provides:
- Mconfigs for configuration of core gateway service configurations (e.g. magmad, eventd, state)
- Metrics exporting to Prometheus
- CRUD API for core Orchestrator network entities (networks, gateways, upgrade tiers, events, etc.)

This charm is part of [Charmed Magma Orchestrator](https://charmhub.io/magma-orc8r/) and should
be deployed as a bundle.

## Usage

```bash
juju deploy magma-orc8r-orchestrator orc8r-orchestrator
juju deploy magma-orc8r-certifier --config domain=example.com orc8r-certifier
juju relate orc8r-orchestrator orc8r-certifier
```

> **Warning**: Deploying this charm must be done with an alias as shown above.


## Relations

### Requires

- **metrics-endpoint**: Relation that provides the metrics endpoints. This interface was only
tested with the `prometheus-k8s` charm.
- **cert-admin-operator**: Relation that provides the admin-operator certificates.

### Provides

- **magma-orc8r-orchestrator**: Used to retrieve the workload service status.

## Actions

### set-log-verbosity
Here is an example of setting the log level to 10 for the `obsidian` service:

```bash
juju run-action orc8r-orchestrator/0 set-log-verbosity level=10 service=obsidian
```

The default log level is 0 and the full log level is 10. 

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0
