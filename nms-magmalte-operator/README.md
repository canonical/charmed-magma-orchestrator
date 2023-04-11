# magma-nms-magmalte

## Description

Magma’s NMS provides a single pane of glass for managing Magma based networks. NMS provides the
ability to configure gateways and associated eNodeBs, provides visibility into status, events and
metrics observed in these networks and finally ability to configure and receive alerts. This charm 
deploys Magmalte which is a microservice built using express framework. It contains set of 
application and router level middlewares. It uses sequelize ORM to connect to the NMS DB for 
servicing any routes involving DB interaction. Visit 
[Magma NMS Overview](https://docs.magmacore.org/docs/nms/nms_arch_overview) to learn more.

This charm is part of [Charmed Magma Orchestrator](https://charmhub.io/magma-orc8r/) and should
be deployed as a bundle.

## Usage

```bash
juju deploy magma-nms-magmalte nms-magmalte
juju deploy postgresql-k8s
juju deploy magma-orc8r-certifier orc8r-certifier --config domain=<your domain>
juju relate nms-magmalte postgresql-k8s:db
juju relate nms-magmalte orc8r-certifier
```

> **Warning**: Deploying this charm must be done with an alias as shown above.

## Actions

### get-host-admin-credentials

```bash
juju run-action nms-magmalte/leader get-host-admin-credentials --wait
```

### create-nms-admin-user

```bash
juju run-action nms-magmalte/leader create-nms-admin-user \
  email=banana@fruits.com \
  password=yellow \
  organization=fruits \
  --wait
```

## Relations

### Requires

- **cert-admin-operator**: Relation that provides the admin-operator certificates.
- **db**: Relation that provides database connectivity.

### Provides

- **magma-nms-magmalte**: Used to retrieve the workload service status.

## OCI Images

Default: ghcr.io/canonical/magma-orc8r-nms-magmalte:1.8.0

