# magma-nms-nginx-proxy

## Description

Magma’s NMS provides a single pane of glass for managing Magma based networks. NMS provides the
ability to configure gateways and associated eNodeBs, provides visibility into status, events and
metrics observed in these networks and finally ability to configure and receive alerts.This charm 
deploys an **nginx** web server that proxies communication between NMS UI and MagmaLTE. Visit 
[Magma NMS Overview](https://docs.magmacore.org/docs/nms/nms_arch_overview) to learn more.

This charm is part of [Charmed Magma Orchestrator](https://charmhub.io/magma-orc8r/) and should
be deployed as a bundle.

## Usage

```bash
juju deploy magma-nms-nginx-proxy nms-nginx-proxy
juju deploy magma-nms-magmalte nms-magmalte
juju deploy magma-orc8r-certifier --config domain=<your domain> orc8r-certifier
juju relate nms-nginx-proxy orc8r-certifier
juju relate nms-nginx-proxy nms-magmalte
```

> **Warning**: Deploying this charm must be done with an alias as shown above.

## Relations

### Requires

- **cert-controller**: Relation that provides the admin-operator certificates.
- **magma-nms-magmalte**: Used to retrieve the workload service status.

## OCI Images

Default: nginx:latest
