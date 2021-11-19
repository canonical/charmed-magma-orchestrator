# orc8r-policydb

## Description

policydb is Magma Orchestrator's service which manages subscriber policies via a northbound 
CRUD API and a southbound policy stream. It belongs to Magma's LTE module.
<br>
Visit [Magma Architecture Overview](https://docs.magmacore.org/docs/orc8r/architecture_overview) 
to learn more.

This [Juju](https://juju.is/) Charm deploys **magma-orc8r-policydb** service.<br>
This charm is part of the [Charmed Magma bundle](https://github.com/canonical/magma-orc8r-dev).

## Usage

**magma-orc8r-policydb** can be deployed via Juju command line using below commands:

```bash
juju deploy ./magma-orc8r-policydb_ubuntu-20.04-amd64.charm \
  --resource magma-orc8r-policydb-image=docker.artifactory.magmacore.org/controller:1.6.0
```

To work correctly, **magma-orc8r-policydb** requires **postgresql-k8s** (for details, check the 
_Relations_ section below).

To deploy **postgresql-k8s** from Juju command line:

```bash
juju deploy postgresql-k8s
juju relate magma-orc8r-policydb postgresql-k8s:db
```

Before running any **juju deploy** commands, make sure charm has been built using:
```bash
charmcraft pack
```

## Relations

Currently supported relations are:

- [postgresql-k8s](https://charmhub.io/postgresql-k8s)

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0

## Contributing

Please see `CONTRIBUTING.md` for developer guidance.
