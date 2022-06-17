# How-to: Deploy Magma Orchestrator on MicroK8s

## Overview

The goal of this document is to detail how to deploy Magma's Orchestrator on MicroK8s. To do so,
we will setup MicroK8s, bootstrap a Juju controller, deploy Magma Orchestrator and configure A
records.

### Pre-requisites

- Ubuntu 20.04 machine

## 1. Install MicroK8s

Install and configure MicroK8s on your Ubuntu machine following the
[official documentation](https://microk8s.io/docs/getting-started).

Enable the following add-ons:

```bash
microk8s enable ingress dns storage
```

Enable MetalLB:

```bash
microk8s enable metallb <your ip range>
```

Replace `<your ip range>` with the range of your choice that contains at least 5 addreses.

## 2. Install and bootstrap Juju

Install Juju following the [official documentation](https://juju.is/docs/olm/installing-juju).

Create a Juju controller:

```bash
juju bootstrap microk8s <your controller name>
```

Replace `<your controller name>` with te name of your choice.

Create a Juju model:

```bash
juju add-model <your model name>
```

## 3. Deploy charmed magma orchestrator

Create an `overlay.yaml` file that contains the following:

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

## 4. Create the orchestrator admin user

Create the user:

```bash
juju run-action orc8r-orchestrator/0 create-orchestrator-admin-user
```

## 5. Setup DNS

Add the following entries to your `/etc/hosts` file:

```text
<orc8r-bootstrap-nginx External IP>   bootstrapper-controller.<your domain>
<orc8r-nginx-proxy External IP>       api.<your domain>
<orc8r-clientcert-nginx External IP>  controller.<your domain>
<nginx-proxy External IP>             *.nms.<your domain>
```

Here replace `<your domain>` with your actual domain name and `<xxx External IP>` with the external
IP's of the specified Kubernetes services.

> **_NOTE:_** External IP's can be retrieved with `kubectl get services -n <your model name> | grep LoadBalancer `


## 6. Verify the deployment

Get the master organization's username and password:

```bash
juju run-action nms-magmalte/0 get-master-admin-credentials --wait
```

Confirm successful deployment by visiting `https://master.nms.<your domain>` and logging in
with the `admin-username` and `admin-password` outputted here.
