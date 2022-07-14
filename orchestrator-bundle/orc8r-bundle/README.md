# magma-orc8r

Orchestrator is a Magma component that provides a simple and consistent way to
configure and monitor the wireless network securely. The metrics acquired through the platform
allows you to see the analytics and traffic flows of the wireless users through the Magma web UI.

This charm bundle makes it easy to deploy the Orchestrator component in any Kubernetes environment,
and it has been tested with all major public cloud platforms.

For more information about Magma, see the official documentation [here](https://magmacore.org/).

## How-to: Deploy Charmed Magma Orchestrator using Juju

This how-to guide can be used to deploy Magma's Orchestrator on any cloud environment. It contains
steps to set up a Kubernetes cluster, bootstrap a Juju controller, deploy charmed operators for
Magma Orchestrator and configure DNS A records. For more information on Charmed Magma, please visit
the project's [homepage](https://github.com/canonical/charmed-magma).

### Pre-requisites

- Ubuntu 20.04 machine with internet access
- A public domain

### 1. Set up your management environment

From a Ubuntu 20.04 machine, install the following tools:

- [Juju](https://juju.is/docs/olm/installing-juju)
- [kubectl](https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/)

### 2. Create a Kubernetes cluster and bootstrap a Juju controller

Select a Kubernetes environment and follow the guide to create the cluster and bootstrap
a Juju controller on it.

1. [MicroK8s](https://juju.is/docs/olm/microk8s)
3. [Google Cloud (GKE)](https://juju.is/docs/olm/google-kubernetes-engine-(gke))
4. [Amazon Web Services (EKS)](https://juju.is/docs/olm/amazon-elastic-kubernetes-service-(amazon-eks)#heading--install-the-juju-client)
5. [Microsoft Azure (AKS)](<https://juju.is/docs/olm/azure-kubernetes-service-(azure-aks)>)

### 3. Deploy charmed Magma Orchestrator

From your Ubuntu machine, create an `overlay.yaml` file that contains the following content:

```yaml
applications:
  orc8r-certifier:
    options:
      domain: <your domain name>
```

Replace `<your domain name>` with your domain name.

Deploy Orchestrator:

```bash
juju deploy magma-orc8r --overlay overlay.yaml --trust --channel=edge
```

The deployment is completed when all services are in the `Active-Idle` state.

### 4. Import the admin operator HTTPS certificate

Retrieve the self-signed certificate:

```bash
juju scp --container="magma-orc8r-certifier" orc8r-certifier/0:/var/opt/magma/certs/..data/admin_operator.pfx admin_operator.pfx
```

> The default password to open the admin_operator.pfx file is `password123`. To choose a different
> password, re-deploy orc8r-certifier with the `passphrase` juju config.

### 5. Setup DNS

Use `kubectl` or your cloud's CLI to retrieve the public addresses associated to the following Kubernetes
LoadBalancer services:

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

### 7. Verify the deployment

Get the master organization's username and password:

```bash
juju run-action nms-magmalte/0 get-master-admin-credentials --wait
```

Confirm successful deployment by visiting `https://master.nms.<your domain>` and logging in
with the `admin-username` and `admin-password` outputted here.

## How-to: Integrate Magma Orchestrator with elasticsearch

From the same environment where orchestrator was deployed, run:
```bash
juju config orc8r-eventd elasticsearch-url=<elasticsearch url>:<elasticsearch port>
juju config orc8r-orchestrator elasticsearch-url=<elasticsearch url>:<elasticsearch port>
```

Where `<elasticsearch url>` and `<elasticsearch port>` are your elasticsearch instance's url and port.
This address must be accessible from the environment where orchestrator is installed.
