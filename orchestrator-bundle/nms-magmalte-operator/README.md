# magma-nms-magmalte

## Description

Magma’s NMS provides a single pane of glass for managing Magma based networks. NMS provides the
ability to configure gateways and associated eNodeBs, provides visibility into status, events and
metrics observed in these networks and finally ability to configure and receive alerts.
<br>
Visit [Magma NMS Overview](https://docs.magmacore.org/docs/nms/nms_arch_overview) to learn more.

This [Juju](https://juju.is/) Charm deploys 
[Magmalte](https://docs.magmacore.org/docs/nms/nms_arch_overview#magmalte) which is a microservice 
built using express framework. It contains set of application and router level middlewares. It uses
sequelize ORM to connect to the NMS DB for servicing any routes involving DB interaction.

This charm is part of the [Charmed Magma bundle](https://github.com/canonical/magma-orc8r-dev).

## Usage

**magma-nms-magmalte** can be deployed via Juju command line using below commands:

```bash
juju deploy ./magma-nms-magmalte_ubuntu-20.04-amd64.charm \
    --resource magma-nms-magmalte-image=docker.artifactory.magmacore.org/magmalte:1.6.0
```

To work correctly, **magma-nms-magmalte** requires **magma-orc8r-certifier** and **postgresql-k8s** (for
details, check the _Relations_ section below).

To deploy **magma-orc8r-certifier** from Juju command line:

```bash
juju deploy ../orc8r-certifier-operator/magma-orc8r-certifier_ubuntu-20.04-amd64.charm --resource magma-orc8r-certifier-image=docker.artifactory.magmacore.org/controller:1.6.0 --config domain=example.com
juju relate magma-nms-magmalte magma-orc8r-certifier
```

To deploy **postgresql-k8s** from Juju command line:

```bash
juju deploy postgresql-k8s
juju relate magma-nms-magmalte postgresql-k8s:db
```

Before running **juju deploy** commands for **magma-nms-magmalte** and **magma-orc8r-certifier**, make sure 
charms have been built using:
```bash
charmcraft pack
```


## Relations

Currently supported relations are:

- [magma-orc8r-certifier](https://github.com/canonical/charmed-magma/tree/main/orchestrator-bundle/orc8r-certifier-operator) -
  magma-orc8r-certifier maintains and verifies signed client certificates and their associated
  identities.
- [postgresql-k8s](https://charmhub.io/postgresql-k8s) - SQL store for magmalte service.

## OCI Images

Default: docker.artifactory.magmacore.org/magmalte:1.6.0

## Contributing

Please see `CONTRIBUTING.md` for developer guidance.
