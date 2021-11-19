# orc8r-certifier

## Description
magma-orc8r-certifier maintains and verifies signed client certificates and their associated
identities.

## Usage

```bash
juju deploy postgresql-k8s
juju deploy ./magma-orc8r-certifier_ubuntu-20.04-amd64.charm \
  --resource magma-orc8r-certifier-image=docker.artifactory.magmacore.org/controller:1.6.0 \
  --config domain=example.com
juju relate magma-orc8r-certifier postgresql-k8s:db
```


## Configuration
- **use-self-signed-ssl-certs** (default: True) - For development deployments only! For production set this to **False**
- **admin-operator-key-pem** - Allows passing own trusted cert (see [magma](https://www.magmacore.org/) for details)
- **admin-operator-pem** - Allows passing own trusted cert (see [magma](https://www.magmacore.org/) for details)
- **controller-crt** - Allows passing own trusted cert (see [magma](https://www.magmacore.org/) for details)
- **controller-key** - Allows passing own trusted cert (see [magma](https://www.magmacore.org/) for details)
- **domain** - Domain for self-signed certs. Use only when **use-self-signed-ssl-certs** set to **True**

## Relations

### Provides

The magma-orc8r-certifier charm provides SSL certificates for charms through the **certs** interface of a **certifier** relation.

### Requires
The magma-orc8r-certifier service relies on a relation to a Database. 

The current setup has only been tested with relation to the `postgresql-k8s` charm.

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0

## Contributing

Please see [CONTRIBUTING](../CONTRIBUTING.md] for developer guidance.
