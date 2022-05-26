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


## Configuration
- **domain** - Domain for self-signed certs. Use only when **use-self-signed-ssl-certs** set to **True**

> Note that once configs have been applied to orc8r-certifier, it is not possible to re-configure.
> To change config, please re-deploy it with the correct config.

### Usage

```bash
juju deploy ./magma-orc8r-certifier_ubuntu-20.04-amd64.charm orc8r-certifier \
 --config domain="whatever.domain" \
 --resource magma-orc8r-certifier-image=docker.artifactory.magmacore.org/controller:1.6.0
```

## Relations

### Provides

The magma-orc8r-certifier does not provide any relationship.

### Requires
The magma-orc8r-certifier service relies on the following relationships:
- `db`: Relation to a database. The current setup has only been tested with relation to the 
`postgresql-k8s` charm
- `tls-certificates`: Relation to a tls-certificates provider. The current setup has only been 
tested with relation to the `vault-k8s` charm

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0
