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
```

> **Warning**: Deploying this charm must be done with an alias as shown above.

## Relations

### Requires

- **cert-bootstrapper**: Relation that provides the bootstrapper private key.

### Provides

- **magma-orc8r-bootstrapper**: Used to retrieve the workload service status.

## OCI Images

Default: linuxfoundation.jfrog.io/magma-docker/controller:1.6.0
