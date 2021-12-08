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

### 3. Juju
- Install Juju following the [official documentation](https://juju.is/docs/olm/installing-juju).
- Create a Juju controller:

```bash
juju bootstrap microk8s microk8s-localhost
```

- Create a new Juju model:

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
- [Ubuntu](https://ubuntu.com/)
- [Microk8s](https://microk8s.io/)
- [Juju](https://juju.is/docs)
- [Magma](https://docs.magmacore.org/docs/basics/introduction.html)
- [Orchestrator](https://docs.magmacore.org/docs/orc8r/architecture_overview)
