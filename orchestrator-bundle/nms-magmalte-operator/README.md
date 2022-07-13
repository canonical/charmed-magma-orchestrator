# magma-nms-magmalte

## Description

Magma’s NMS provides a single pane of glass for managing Magma based networks. NMS provides the
ability to configure gateways and associated eNodeBs, provides visibility into status, events and
metrics observed in these networks and finally ability to configure and receive alerts.

## Usage

```bash
juju deploy magma-nms-magmalte nms-magmalte
juju deploy postgresql-k8s
juju deploy magma-orc8r-certifier orc8r-certifier --config domain=example.com 
juju relate nms-magmalte postgresql-k8s:db
juju relate nms-magmalte orc8r-certifier
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

## Actions

### get-master-admin-credentials

```bash
juju run-action nms-magmalte/leader get-master-admin-credentials --wait
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

Default: docker.artifactory.magmacore.org/magmalte:1.6.0
