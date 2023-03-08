# magma-orc8r-tenants

## Description
magma-orc8r-tenants provides CRUD interface for managing NMS tenants.

## Usage

```bash
juju deploy postgresql-k8s
juju deploy magma-orc8r-tenants orc8r-tenants
juju relate orc8r-tenants postgresql-k8s:db
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

## Relations
The magma-orc8r-tenants service relies on a relation to `postgresql-k8s`. 

## OCI Images
Default: ghcr.io/canonical/magma-orc8r-controller:1.8.0
