# magma-orc8r

## Overview
Orchestrator is a Magma service that provides a simple and consistent way to 
configure and monitor the wireless network securely. The metrics acquired through the platform 
allows you to see the analytics and traffic flows of the wireless users through the Magma web UI.

## Usage

In order for the bundle to be deployed with your domain, we need to create an overlay bundle file. 
This file should contain the following:

```yaml
applications:
  orc8r-certifier:
    options:
      domain: <your domain>

```

An example with the same content is provided in `overlay_examples/self_signed_certs.yaml` and you 
can read more about overlay bundles 
[here](https://discourse.charmhub.io/t/how-to-manage-charm-bundles/1058#heading--overlay-bundles).
An example for the case where you'd want to provide your own certificates is also presented.

Deploy the `magma-orc8r` bundle specifying your overlay bundle file.
```bash
juju deploy magma-orc8r --overlay ~/self_signed_certs.yaml --trust
```

## Configure

### Create Orchestrator admin user

The NMS requires some basic certificate-based authentication when making calls to the Orchestrator 
API. To support this, we need to add the relevant certificate as an admin user to the controller.

```bash
juju run-action orc8r-orchestrator/0 create-orchestrator-admin-user
```

### Create NMS admin user

Create an admin user for the master organization on the NMS. Here specify an email and password that 
you will want to use when connecting to NMS as an admin.

```bash
juju run-action nms-magmalte/0 create-nms-admin-user email=<your email> password=<your password>
```

### Change log verbosity
You can set the log level of any service using the `set-log-verbosity` action. The default log
level is 0 and the full log level is 10. Here is an example of setting the log level to 10 for the 
`obsidian` service:

```bash
juju run-action orc8r-orchestrator/0 set-log-verbosity level=10 service=obsidian
```


## DNS Resolution
Some services will have to be exposed to outside of the Kubernetes cluster. This is done by 
associating LoadBalancer addresses to resolvable domains. Here is the association of Kubernetes 
service to record that you will have to implement:


| Kubernetes service       | Record name                             | 
|:-------------------------|:----------------------------------------|
| `nginx-proxy`            | `*.nms.<your domain>`                   |
| `orc8r-bootstrap-nginx`  | `bootstrapper-controller.<your domain>` |
| `orc8r-clientcert-nginx` | `controller.<your domain>`              |
| `orc8r-nginx-proxy`      | `api.<your domain>`                     | 

For more details, please refer to the documentation provided for your specific 
cloud provider.


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

## Debug
Logs can be found by querying each individual pod. Example:

```bash
kubectl logs nms-magmalte-0 -c magma-nms-magmalte -n <your model> --follow
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
- [Juju](https://juju.is/docs)
- [Magma](https://docs.magmacore.org/docs/basics/introduction.html)
- [Orchestrator](https://docs.magmacore.org/docs/orc8r/architecture_overview)
