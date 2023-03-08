# magma-orc8r-bootstrapper

## Description

magma-orc8r-bootstrapper manages the certificate bootstrapping process for newly registered 
gateways and gateways whose cert has expired.

This charm is part of [Charmed Magma Orchestrator](https://charmhub.io/magma-orc8r/) and should
be deployed as a bundle.

## Usage

```bash
juju deploy magma-orc8r-bootstrapper orc8r-bootstrapper
juju relate orc8r-bootstrapper orc8r-certifier
juju relate orc8r-bootstrapper postgresql-k8s:db
juju relate orc8r-bootstrapper:cert-root-ca orc8r-certifier:cert-root-ca
```

> **Warning**: Deploying this charm must be done with an alias as shown above.

## Relations

### Requires

- **cert-bootstrapper**: Relation that provides the bootstrapper private key.
- **cert-root-ca**: Relation that provides the rootCA certificates.
- **db**: Relation that provides database connectivity.

### Provides

- **magma-orc8r-bootstrapper**: Used to retrieve the workload service status.

## OCI Images

Default: ghcr.io/canonical/magma-orc8r-controller:1.8.0
