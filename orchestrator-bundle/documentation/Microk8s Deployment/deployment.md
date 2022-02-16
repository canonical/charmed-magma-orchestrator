# Deploying Magma on: Microk8s

## Overview
Orchestrator is a Magma service that provides a simple and consistent way to 
configure and monitor the wireless network securely. The metrics acquired through the platform 
allows you to see the analytics and traffic flows of the wireless users through the Magma web UI.


## Hardware requirements
- CPU: 8 vCPU's
- Memory: 32 GB
- Storage: 100 GB

## Pre-requisites
This bundle of charms requires the following:
1. Ubuntu (20.04)
2. Microk8s (v1.22.4)
3. Juju (2.9.21)

### 1. Ubuntu
- Install Ubuntu following the [official documentation](https://releases.ubuntu.com/20.04/).

### 2. Microk8s
- Install and configure Microk8s on your Ubuntu VM following the 
[official documentation](https://microk8s.io/docs/getting-started).
- Enable the following add-ons:

```bash
microk8s enable ingress dns storage
```
- Enable MetalLB. You need to provide an IP address pool that MetalLB will hand out IPs from. A 
pool of four will be enough.

```bash
microk8s enable metallb 10.0.0.1-10.0.0.5
```

### 3. Juju
- Install Juju following the [official documentation](https://juju.is/docs/olm/installing-juju).
- Create a Juju controller:

```bash
juju bootstrap microk8s microk8s-localhost
```

- Create a new Juju model:

```bash
juju add-model <your model name>
```

## Usage

To deploy magma-orc8r, you will first need to create an `overlay.yaml` file that will contain
the domain name that you will be using. Once you replaced `<your domain name>` with your domain 
name, you can deploy orchestrator:

```bash
juju deploy magma-orc8r --overlay overlay.yaml --trust
```

## DNS Resolution

Services are to be accessed via domain names. To do so, you will need to map certain addresses to 
their LoadBalancer IP addresses. Retrieve the IP addresses given to your services.

```bash
kubectl get services -n <your model name> | grep LoadBalancer
```

The output should look like this (but with different IP's):

```bash
orc8r-bootstrap-nginx          LoadBalancer   10.152.183.151   10.0.0.1      80:31200/TCP,443:30747/TCP,8444:30618/TCP                  5h41m
orc8r-nginx-proxy              LoadBalancer   10.152.183.75    10.0.0.2      80:32035/TCP,8443:30130/TCP,8444:31694/TCP,443:30794/TCP   22h
orc8r-clientcert-nginx         LoadBalancer   10.152.183.181   10.0.0.3      80:31641/TCP,443:31082/TCP,8443:31811/TCP                  5h41m
nginx-proxy                    LoadBalancer   10.152.183.249   10.0.0.4      443:30760/TCP                                              44s
```

If you self-host magma and you don't want to make changes to your DNS server, you will have to
update your `/etc/hosts` file so that you can reach orc8r via its domain name. Add the following 
entries to your `/etc/hosts` file (your actual IP's may differ)

```text
10.0.0.1 bootstrapper-controller.<your domain>
10.0.0.2 api.<your domain>
10.0.0.3 controller.<your domain>
10.0.0.4 master.nms.<your domain>
10.0.0.4 magma-test.nms.<your domain>
```
Here replace `<your domain>` with your actual domain name.


## Configure

The NMS requires some basic certificate-based authentication when making calls to the Orchestrator 
API. To support this, we need to add the relevant certificate as an admin user to the controller.

```bash
juju run-action orc8r-orchestrator/0 create-orchestrator-admin-user
```

Create an admin user for the master organization on the NMS. Here specify an email and password that 
you will want to use when connecting to NMS as an admin.

```bash
juju run-action nms-magmalte/0 create-nms-admin-user email=<your email> password=<your password>
```

## Verify the Deployment
### NMS 
You can confirm successful deployment by visiting the master NMS organization at e.g. 
`https://master.nms.<your domain>` and logging in with your email and password provided above 
(`<your email>` and `<your password>` in this example).
If you self-signed certs above, the browser will rightfully complain. 
Either ignore the browser warnings at your own risk (some versions of Chrome won't 
allow this at all), or e.g. import the root CA from above on a per-browser basis.

### Orchestrator
For interacting with the Orchestrator REST API, a good starting point is the Swagger UI available 
at `https://api.<your domain>/swagger/v1/ui/`.

### Juju
You can run `juju status` and you should see all charms are in the `Active-Idle`status.

### Kubernetes
You can run `kubectl get pods -n <your model>` and you should see that all pods are up and 
running.
