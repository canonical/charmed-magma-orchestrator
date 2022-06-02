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


## Relations

### Provides

This charm provides no relation.

### Requires

The following relation is required:

- admin_operator: This relation is provided by the `nms-magmalte` charm

## Actions

### Create orchestrator admin user

```bash
juju run-action orc8r-orchestrator/0 create-orchestrator-admin-user
```

### Set log level
You can set the log level of any service using the `set-log-verbosity` action. The default log
level is 0 and the full log level is 10. Here is an example of setting the log level to 10 for the 
`obsidian` service:

```bash
juju run-action orc8r-orchestrator/0 set-log-verbosity level=10 service=obsidian
```

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0
