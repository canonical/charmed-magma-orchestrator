# How-to: Deploy Magma Orchestrator on GCP with GKE

The goal of this document is to detail how to deploy Magma's Orchestrator on GCP with GKE. To do so,
we will set up a GKE cluster, bootstrap a Juju controller, deploy Magma Orchestrator and configure A
records.

### Pre-requisites

- Ubuntu 20.04 machine with internet access
- A public domain

## 1. Set up your management environment

From a Ubuntu 20.04 machine, install the following tools:

- [Juju](https://juju.is/docs/olm/installing-juju)
- [kubectl](https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/)

## 2. Deploy Kubernetes on GCP using GKE

Follow this [guide](<https://juju.is/docs/olm/google-kubernetes-engine-(gke)>) to deploy a
Kubernetes cluster using GKE and bootstrap a Juju controller.

## 3. Deploy charmed magma orchestrator

From your Ubuntu machine, create an `overlay.yaml` file that contains the following:

```yaml
applications:
  orc8r-certifier:
    options:
      domain: <your domain name>
```

Replace `<your domain name>` with your domain name.

Deploy orchestrator:

```bash
juju deploy magma-orc8r --overlay overlay.yaml --trust --channel=edge
```

The deployment is completed when all services are in the `Active-Idle` state.

## 4. Import the HTTPS Certificate

Retrieve the self-signed certificate:

```bash
juju scp orc8r-certifier/0:/var/opt/magma/certs/admin_operator.pfx admin_operator.pfx
```

The default password is `password123`.

> **_NOTE:_** The default password can be changed by deploying the certifier charm using
> the Juju config `passphrase`.

## 5. Setup Orchestrator

Create the Orchestrator admin user:

```bash
juju run-action orc8r-orchestrator/0 create-orchestrator-admin-user
```

Get the master organization's username and password:

```bash
juju run-action nms-magmalte/0 get-admin-credentials --wait
```

## 6. Setup DNS

Navigate to the GCP Console -> GKE -> Services & Ingress and note the addresses associated to the
following services:

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

## 7. Verify the deployment

Confirm successful deployment by visiting `https://master.nms.<your domain>` and logging in
with the `<admin email>` and `<admin password>` provided above.
