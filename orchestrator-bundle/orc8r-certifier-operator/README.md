# magma-orc8r-certifier

## Description
magma-orc8r-certifier maintains and verifies signed client certificates and their associated
identities.

## Usage

```bash
juju deploy postgresql-k8s
juju deploy vault-k8s
juju deploy magma-orc8r-certifier --config domain=example.com orc8r-certifier
juju relate orc8r-certifier postgresql-k8s:db
juju relate orc8r-certifier vault-k8s
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.


### Import the admin operator HTTPS certificate

Retrieve the certificates to authenticate against Magma:

```bash
juju scp --container="magma-orc8r-certifier" orc8r-certifier/0:/var/opt/magma/certs/admin_operator.pfx admin_operator.pfx
```

Retrieve the password to open the pfx package:

```bash
juju run-action orc8r-certifier/leader get-pfx-package-password --wait
```

The pfx package can now be loaded in your browser.

## Configuration

The domain name is needed for TLS certificates generation:
- **domain** - Domain for self-signed certificate generation. 

## Relations

### Provides

magma-orc8r-certifier provides the following relations:
- **cert-admin-operator**: TODO
- **cert-controller**: TODO
- **cert-certifier**: TODO

### Requires
magma-orc8r-certifier relies on two relations:
- **db**: Validation was done using `postgresql-k8s`
- **tls-certificates**: Relations supported are tls-certificates-operator for certificates provided by 
user and vault-k8s (for self-signed certificates)


## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0
