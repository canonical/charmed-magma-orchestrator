# magma-orc8r-bootstrapper

## Description
magma-orc8r-bootstrapper manages the certificate bootstrapping process for newly registered 
gateways and gateways whose cert has expired

## Usage

```bash
juju deploy magma-orc8r-bootstrapper orc8r-bootstrapper
juju relate orc8r-bootstrapper orc8r-certifier
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

## OCI Images
Default: docker.artifactory.magmacore.org/controller:1.7.0
