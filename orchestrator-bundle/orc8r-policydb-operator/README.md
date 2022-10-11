# magma-orc8r-policydb

## Description

magma-orc8r-policydb manages subscriber policies via a northbound CRUD API and a southbound 
policy stream. It belongs to Magma's LTE module.

## Usage

```bash
juju deploy postgresql-k8s
juju deploy magma-orc8r-policydb orc8r-policydb
juju relate orc8r-policydb postgresql-k8s:db
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0
