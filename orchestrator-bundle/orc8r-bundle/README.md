# magma-orc8r

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
- Ubuntu (20.04)
- Microk8s (v1.22.4)
- Juju (2.9.21)

### Ubuntu
For installing Ubuntu, please follow the [official documentation](https://releases.ubuntu.com/20.04/).

### Microk8s
On your Ubuntu VM, install microk8s using snap:

```bash
sudo snap install microk8s --classic
```
Update your user's permission to be added to the microk8s group

```bash
sudo usermod -a -G microk8s $USER
sudo chown -f -R $USER ~/.kube
newgrp microk8s
```

Enable the following add-ons to your microk8s cluster:

```bash
microk8s enable ingress dns storage
```

### Juju
Install Juju using snap:

```bash
sudo snap install juju --classic
```

Create a Juju controller which is the management node of a Juju cloud environment:

```bash
juju bootstrap microk8s microk8s-localhost
```

Create a new Juju model. Generally speaking, a model is a workspace and in the case of Kubernetes, it
is simply a new namespace.

```bash
juju add-model orchestrator
```

## Usage

```bash
juju deploy magma-orc8r
```

## Detailed content
Orchestrator is made up of multiple services and this bundle contains a charm per service:
- [magma-nms-magmalte](https://charmhub.io/magma-nms-magmalte)
- [magma-nms-nginx-proxy](https://charmhub.io/magma-nms-nginx-proxy)
- [magma-orc8r-accessd](https://charmhub.io/magma-orc8r-accessd)
- [magma-orc8r-analytics](https://charmhub.io/magma-orc8r-analytics)
- [magma-orc8r-bootstrapper](https://charmhub.io/magma-orc8r-bootstrapper)
- [magma-orc8r-certifier](https://charmhub.io/magma-orc8r-certifier)
- [magma-orc8r-configurator](https://charmhub.io/magma-orc8r-configurator)
- [magma-orc8r-ctraced](https://charmhub.io/magma-orc8r-ctraced)
- [magma-orc8r-device](https://charmhub.io/magma-orc8r-device)
- [magma-orc8r-directoryd](https://charmhub.io/magma-orc8r-directoryd)
- [magma-orc8r-dispatcher](https://charmhub.io/magma-orc8r-dispatcher)
- [magma-orc8r-eventd](https://charmhub.io/magma-orc8r-eventd)
- [magma-orc8r-ha](https://charmhub.io/magma-orc8r-ha)
- [magma-orc8r-lte](https://charmhub.io/magma-orc8r-lte)
- [magma-orc8r-metricsd](https://charmhub.io/magma-orc8r-metricsd)
- [magma-orc8r-nginx](https://charmhub.io/magma-orc8r-nginx)
- [magma-orc8r-obsidian](https://charmhub.io/magma-orc8r-obsidian)
- [magma-orc8r-orchestrator](https://charmhub.io/magma-orc8r-orchestrator)
- [magma-orc8r-policydb](https://charmhub.io/magma-orc8r-policydb)
- [magma-orc8r-service-registry](https://charmhub.io/magma-orc8r-service-registry)
- [magma-orc8r-smsd](https://charmhub.io/magma-orc8r-smsd)
- [magma-orc8r-state](https://charmhub.io/magma-orc8r-state)
- [magma-orc8r-streamer](https://charmhub.io/magma-orc8r-streamer)
- [magma-orc8r-subscriberdb](https://charmhub.io/magma-orc8r-subscriberdb)
- [magma-orc8r-subscriberdb-cache](https://charmhub.io/magma-orc8r-subscriberdb-cache)
- [magma-orc8r-tenants](https://charmhub.io/magma-orc8r-tenants)

## References
- [Magma documentation](https://docs.magmacore.org/docs/basics/introduction.html)
- [Orchestrator documentation](https://docs.magmacore.org/docs/orc8r/architecture_overview)
