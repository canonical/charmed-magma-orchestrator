# magma-orc8r-policydb

## Description

magma-orc8r-policydb is Magma Orchestrator's service which manages subscriber policies via a northbound 
CRUD API and a southbound policy stream. It belongs to Magma's LTE module.
<br>
Visit [Magma Architecture Overview](https://docs.magmacore.org/docs/orc8r/architecture_overview) 
to learn more.

This [Juju](https://juju.is/) Charm deploys **magma-orc8r-policydb** service.<br>
This charm is part of the [Charmed Magma bundle](https://github.com/canonical/charmed-magma).

## Usage

**magma-orc8r-policydb** can be deployed via Juju command line using below commands:

```bash
juju deploy magma-orc8r-policydb orc8r-policydb
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

To work correctly, **magma-orc8r-policydb** requires **postgresql-k8s** (for details, check the 
_Relations_ section below).

To deploy **postgresql-k8s** from Juju command line:

```bash
juju deploy postgresql-k8s
juju relate orc8r-policydb postgresql-k8s:db
```

Before running any **juju deploy** commands, make sure charm has been built using:
```bash
charmcraft pack
```

## Relations

Currently supported relations are:

- [postgresql-k8s](https://charmhub.io/postgresql-k8s)

## OCI Images

Default: docker-ci.artifactory.magmacore.org/controller:13029
