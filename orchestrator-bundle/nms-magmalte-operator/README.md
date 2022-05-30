# magma-nms-magmalte

## Description

Magma’s NMS provides a single pane of glass for managing Magma based networks. NMS provides the
ability to configure gateways and associated eNodeBs, provides visibility into status, events and
metrics observed in these networks and finally ability to configure and receive alerts.
Visit [Magma NMS Overview](https://docs.magmacore.org/docs/nms/nms_arch_overview) to learn more.


## Usage

```bash
juju deploy postgresql-k8s
juju deploy vault-k8s
juju deploy magma-nms-magmalte nms-magmalte
juju relate nms-magmalte postgresql-k8s:db
juju relate nms-magmalte vault-k8s
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.


## Actions

### get-admin-credentials 

```bash
juju run-action nms-magmalte/0 get-admin-credentials --wait
```

## Relations

### Provides

The magma-orc8r-certifier does not provide any relationship.

### Requires
The magma-orc8r-certifier service relies on the following relationships:
- `db`: Relation to a database. The current setup has only been tested with relation to the 
`postgresql-k8s` charm
- `tls-certificates`: Relation to a tls-certificates provider. The current setup has only been 
tested with relation to the `vault-k8s` charm

## OCI Images
Default: docker.artifactory.magmacore.org/magmalte:1.6.0
