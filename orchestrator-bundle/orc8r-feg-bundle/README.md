# magma-orc8r-feg

## Overview

Orchestrator is a Magma service that provides a simple and consistent way to
configure and monitor the wireless network securely. The metrics acquired through the platform
allows you to see the analytics and traffic flows of the wireless users through the Magma web UI.

This charm bundle makes it easy to deploy the Orchestrator component in any Kubernetes environment,
and it has been tested with all major public cloud platforms.

As well as all the base Orchestrator charms, this bundle also includes the required charms to 
manage federation gateways.

For more information about Magma, see the official documentation [here](https://magmacore.org/).

## Usage

### Deploy the bundle

Create an `overlay.yaml` file that contains the following:

```yaml
applications:
  orc8r-certifier:
    options:
      domain: <your domain name>
  orc8r-nginx:
    options:
      domain: <your domain name>
  tls-certificates-operator:
    options:
      certificate: <your base64 encoded certificate>
      private-key: <your base64 encoded private key>
      ca-certificate: <your base64 encoded ca certificate>
```

Alternatively, for non-secure deployments, you can use tls-certificates-operator's  `generate-self-signed-certificates` 
Juju config.

```yaml
applications:
  orc8r-certifier:
    options:
      domain: <your domain name>
  orc8r-nginx:
    options:
      domain: <your domain name>
  tls-certificates-operator:
    options:
      generate-self-signed-certificates: true
```

Deploy orchestrator:

```bash
juju deploy magma-orc8r-feg --overlay overlay.yaml --trust --channel=edge
```

The deployment is completed when all services are in the `Active-Idle` state.

### Import the admin operator HTTPS certificate

Retrieve the certificates to authenticate against Magma Orchestrator:

```bash
juju scp --container="magma-orc8r-certifier" orc8r-certifier/0:/var/opt/magma/certs/admin_operator.pfx admin_operator.pfx
```

Retrieve the password to open the pfx package:

```bash
juju run-action orc8r-certifier/leader get-pfx-package-password --wait
```

The pfx package can now be loaded in your browser.

### Create the orchestrator admin user

Create the user:

```bash
juju run-action orc8r-orchestrator/0 create-orchestrator-admin-user
```

### Setup DNS

Retrieve the services that need to be exposed:

```bash
kubectl get services -n <your model> | grep LoadBalancer
```

Note the addresses associated to the following services:

- `nginx-proxy`
- `orc8r-bootstrap-nginx`
- `orc8r-clientcert-nginx`
- `orc8r-nginx-proxy`

Create these A records in your managed domain:

| Hostname                                | Address                                |
|-----------------------------------------|----------------------------------------|
| `bootstrapper-controller.<your domain>` | `<orc8r-bootstrap-nginx External IP>`  |
| `api.<your domain>`                     | `<orc8r-nginx-proxy External IP>`      |
| `controller.<your domain>`              | `<orc8r-clientcert-nginx External IP>` |
| `*.nms.<your domain>`                   | `<nginx-proxy External IP>`            |


## Verify the deployment

Get the master organization's username and password:

```bash
juju run-action nms-magmalte/0 get-master-admin-credentials --wait
```

Confirm successful deployment by visiting `https://master.nms.<your domain>` and logging in
with the `admin-username` and `admin-password` outputted here.
