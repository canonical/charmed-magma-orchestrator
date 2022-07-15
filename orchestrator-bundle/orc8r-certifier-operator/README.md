# magma-orc8r-certifier

## Description

magma-orc8r-certifier maintains and verifies signed client certificates and their associated
identities.

This charm is part of [Charmed Magma Orchestrator](https://charmhub.io/magma-orc8r/) and should
be deployed as a bundle.

## Usage

```bash
juju deploy postgresql-k8s
juju deploy vault-k8s
juju deploy magma-orc8r-certifier --config domain=example.com orc8r-certifier
juju relate orc8r-certifier postgresql-k8s:db
juju relate orc8r-certifier vault-k8s
```

> **Warning**: Deploying this charm must be done with an alias as shown above.

To import the the admin operator HTTPS certificate, run this command:

```bash
juju scp --container="magma-orc8r-certifier" orc8r-certifier/0:/var/opt/magma/certs/admin_operator.pfx admin_operator.pfx
```

## Actions

### get-pfx-package-password

```bash
juju run-action orc8r-certifier/leader get-pfx-package-password --wait
```

The pfx package can now be loaded in your browser.

## Configuration

- **domain** - Domain for self-signed certificate generation. 

## Relations

### Provides

- **cert-admin-operator**: Relation that provides the admin-operator certificates.
- **cert-bootstrapper**: Relation that provides the bootstrapper private key.
- **cert-controller**: Relation that provides the controller certificates.
- **cert-certifier**: Relation that provides the certifier certificates.

### Requires

- **db**: Validation was done using `postgresql-k8s`
- **tls-certificates**: Relations supported are tls-certificates-operator for certificates provided by 
user and vault-k8s (for self-signed certificates)

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0
