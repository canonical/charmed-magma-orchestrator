# magma-nms-nginx-proxy

## Description

Magma’s NMS provides a single pane of glass for managing Magma based networks. NMS provides the
ability to configure gateways and associated eNodeBs, provides visibility into status, events and
metrics observed in these networks and finally ability to configure and receive alerts.
<br>
Visit [Magma NMS Overview](https://docs.magmacore.org/docs/nms/nms_arch_overview) to learn more.

This [Juju](https://juju.is/) Charm deploys an **nginx** web server that proxies communication
between NMS UI and MagmaLTE.<br>

## Usage

```bash
juju deploy magma-nms-magmalte nms-magmalte
juju deploy vault-k8s
juju deploy magma-nms-nginx-proxy nms-nginx-proxy --config domain=blabla.com
juju relate nms-nginx-proxy nms-magmalte
juju relate nms-nginx-proxy vault-k8s
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

## Configuration
- **domain** - Domain for self-signed certificates.

> Note that once configs have been applied to orc8r-certifier, it is not possible to re-configure.
> To change config, please re-deploy it with the correct config.

## Relations

### Provides

The nms-nginx-proxy charm does not provide any relationship.

### Requires
The nms-nginx-proxy charm relies on the following relationships:
- `magmalte`: Relation to the NMS MagmaLTE service
- `tls-certificates`: Relation to a tls-certificates provider. The current setup has only been 
tested with relation to the `vault-k8s` charm

## OCI Images

Default: nginx:latest
