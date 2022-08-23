# magma-orc8r

## Overview

Orchestrator is a Magma service that provides a simple and consistent way to
configure and monitor the wireless network securely. The metrics acquired through the platform
allows you to see the analytics and traffic flows of the wireless users through the Magma web UI.
For more information about Magma, see the official documentation [here](https://magmacore.org/).

This charm bundle makes it easy to deploy the Orchestrator component in any Kubernetes environment,
and it has been tested with all major public cloud platforms.

## Usage

### Deploy the bundle

From your Ubuntu machine, create an `overlay.yaml` file that contains the following content:

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
      ca-common-name: rootca.<your domain name>
```

> **Warning**: This configuration is unsecure because it uses self-signed certificates.

Deploy Orchestrator:

```bash
juju deploy magma-orc8r --overlay overlay.yaml --trust --channel=edge
```

The deployment is completed when all services are in the `Active-Idle` state.


### Import the admin operator HTTPS certificate

Retrieve the PFX package and password that contains the certificates to authenticate against Magma Orchestrator:

```bash
juju scp --container="magma-orc8r-certifier" orc8r-certifier/0:/var/opt/magma/certs/admin_operator.pfx admin_operator.pfx
juju run-action orc8r-certifier/leader get-pfx-package-password --wait
```

> The pfx package was copied to your current working directory and can now be loaded in your browser.

### Setup DNS

Retrieve the services that need to be exposed:

```bash
juju run-action orc8r-orchestrator/leader get-load-balancer-services --wait
```

In your domain registrar, create A records for the following Kubernetes services:

| Address                                | Hostname                                | 
|----------------------------------------|-----------------------------------------|
| `<orc8r-bootstrap-nginx External IP>`  | `bootstrapper-controller.<your domain>` | 
| `<orc8r-nginx-proxy External IP>`      | `api.<your domain>`                     | 
| `<orc8r-clientcert-nginx External IP>` | `controller.<your domain>`              | 
| `<nginx-proxy External IP>`            | `*.nms.<your domain>`                   | 

### Verify the deployment

Get the master organization's username and password:

```bash
juju run-action nms-magmalte/leader get-master-admin-credentials --wait
```

Confirm successful deployment by visiting `https://master.nms.<your domain>` and logging in
with the `admin-username` and `admin-password` outputted here.
