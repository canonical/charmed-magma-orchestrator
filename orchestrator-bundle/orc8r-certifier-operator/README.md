# magma-orc8r-certifier

## Description
magma-orc8r-certifier maintains and verifies signed client certificates and their associated
identities.

## Usage

```bash
juju deploy postgresql-k8s
juju deploy magma-orc8r-certifier --config domain=example.com orc8r-certifier
juju relate orc8r-certifier postgresql-k8s:db
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.


## Configuration
- **use-self-signed-ssl-certs** (default: True) - For development deployments only! For production set this to **False**
- **admin-operator-key-pem** - Allows passing own trusted cert (see [magma](https://www.magmacore.org/) for details)
- **admin-operator-pem** - Allows passing own trusted cert (see [magma](https://www.magmacore.org/) for details)
- **controller-crt** - Allows passing own trusted cert (see [magma](https://www.magmacore.org/) for details)
- **controller-key** - Allows passing own trusted cert (see [magma](https://www.magmacore.org/) for details)
- **bootstrapper-key** - Allows passing own trusted cert (see [magma](https://www.magmacore.org/) for details)
- **certifier-key** - Allows passing own trusted cert (see [magma](https://www.magmacore.org/) for details)
- **certifier-pem** - Allows passing own trusted cert (see [magma](https://www.magmacore.org/) for details)
- **rootCA-key** - Allows passing own trusted cert (see [magma](https://www.magmacore.org/) for details)
- **rootCA-pem** - Allows passing own trusted cert (see [magma](https://www.magmacore.org/) for details)
- **domain** - Domain for self-signed certs. Use only when **use-self-signed-ssl-certs** set to **True**


### Usage


#### With existing certificates
Here we use a set of certificates based and placed them under the `/home/ubuntu/certs/` directory.

```bash
juju deploy ./magma-orc8r-certifier_ubuntu-20.04-amd64.charm orc8r-certifier \
 --config use-self-signed-ssl-certs=False \
 --config admin-operator-key-pem="$(cat /home/ubuntu/certs/admin_operator.key.pem)" \
 --config admin-operator-pem="$(cat /home/ubuntu/certs/admin_operator.pem)" \
 --config controller-crt="$(cat /home/ubuntu/certs/controller.crt)" \
 --config controller-key="$(cat /home/ubuntu/certs/controller.key)" \
 --config bootstrapper-key="$(cat /home/ubuntu/certs/bootstrapper.key)" \
 --config certifier-key="$(cat /home/ubuntu/certs/certifier.key)" \
 --config certifier-pem="$(cat /home/ubuntu/certs/certifier.pem)" \
 --config rootCA-key="$(cat /home/ubuntu/certs/rootCA.key)" \
 --config rootCA-pem="$(cat /home/ubuntu/certs/rootCA.pem)" \
 --resource magma-orc8r-certifier-image=docker.artifactory.magmacore.org/controller:1.6.0
```

#### With self-signed certificates

```bash
juju deploy ./magma-orc8r-certifier_ubuntu-20.04-amd64.charm orc8r-certifier \
  --config domain=example.com \
  --resource magma-orc8r-certifier-image=docker.artifactory.magmacore.org/controller:1.6.0
```

By default, the passphrase to open the `admin_operator.pfx` file is `password123`. This can be 
changed by deploying the certifier charm using the Juju config `passphrase`.

You can retrieve the `admin_operator.pfx` file using the following command:

```bash
juju scp orc8r-certifier/0:/tmp/certs/admin_operator.pfx admin_operator.pfx
```

The cert can now be loaded in your browser.

## Relations

### Provides

The magma-orc8r-certifier charm provides SSL certificates for charms through the **certs** 
interface of a **certifier** relation.

### Requires
The magma-orc8r-certifier service relies on a relation to a Database. 

The current setup has only been tested with relation to the `postgresql-k8s` charm.

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0
