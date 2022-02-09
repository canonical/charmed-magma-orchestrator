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

### Assemble certificates

First choose a domain name. Here we will use `example.com`. Create a local directory to hold the 
certificates you will use for your Orchestrator deployment.

```bash
mkdir -p ~/certs
cd ~/certs
```

You will need the following certificates and private keys placed in this directory

1. The public SSL certificate for your Orchestrator domain, with `CN=*.yourdomain.com`. 
This can be an SSL certificate chain, but it must be in one file.
2. The private key which corresponds to the above SSL certificate.
3. The root CA certificate which verifies your SSL certificate.

If you aren't worried about a browser warning, you can generate self-signed versions of these 
certs. Though please note that using trusted certs in production deployments is encouraged.

If you want to use self-signed certificates, you can generate certificates by following the 
guidelines on the official magma website [here](https://docs.magmacore.org/docs/orc8r/deploy_install).

At the end, the certs directory should now look like this:

```bash
ubuntu@thinkpad:~$ ls -1 ~/certs/
admin_operator.key.pem
admin_operator.pem
admin_operator.pfx
bootstrapper.key
certifier.key
certifier.pem
controller.crt
controller.key
fluentd.key
fluentd.pem
rootCA.key
rootCA.pem
```

In order for the bundle to be deployed with the above-mentioned certificates and domain, we need
to create an overlay bundle file. This file should contain the following:

```yaml
applications:
  orc8r-certifier:
    options:
      use-self-signed-ssl-certs: False
      admin-operator-key-pem: "$(cat ~/certs/admin_operator.key.pem)"
      admin-operator-pem: "$(cat ~/certs/admin_operator.pem)"
      controller-crt: "$(cat ~/certs/controller.crt)"
      controller-key: "$(cat ~/certs/controller.key)"
      bootstrapper-key: "$(cat ~/certs/bootstrapper.key)"
      certifier-key: "$(cat ~/certs/certifier.key)"
      certifier-pem: "$(cat ~/certs/certifier.pem)"
      rootCA-key: "$(cat ~/certs/rootCA.key)"
      rootCA-pem: "$(cat ~/certs/rootCA.pem)"
      domain: example.com
```
An example with the same content is provided in `overlay-example.yaml` and you can read more about 
overlay bundles 
[here](https://discourse.charmhub.io/t/how-to-manage-charm-bundles/1058#heading--overlay-bundles).

Deploy the `magma-orc8r` bundle specifying your overlay bundle file.
```bash
juju deploy magma-orc8r --overlay ~/overlay-example.yaml
```


## DNS Resolution

Services are to be accessed via domain names. To do so, you will need to map certain addresses to 
their LoadBalancer IP addresses. Retrieve the IP addresses given to your services.

```bash
ubuntu@thinkpad:~$ kubectl get services -n <your model name> | grep LoadBalancer
```

The output should look like this (but with different IP's):

```bash
orc8r-bootstrap-nginx          LoadBalancer   10.152.183.151   10.0.0.1      80:31200/TCP,443:30747/TCP,8444:30618/TCP                  5h41m
orc8r-nginx-proxy              LoadBalancer   10.152.183.75    10.0.0.2      80:32035/TCP,8443:30130/TCP,8444:31694/TCP,443:30794/TCP   22h
orc8r-clientcert-nginx         LoadBalancer   10.152.183.181   10.0.0.3      80:31641/TCP,443:31082/TCP,8443:31811/TCP                  5h41m
nginx-proxy                    LoadBalancer   10.152.183.249   10.0.0.4      443:30760/TCP                                              44s
```

### Self-hosted

If you self-host magma and you don't want to make changes to your DNS server, you will have to
update your `/etc/hosts` file so that you can reach orc8r via its domain name. Add the following 
entries to your `/etc/hosts` file (your actual IP's may differ)

```text
10.0.0.1 bootstrapper-controller.example.com
10.0.0.2 api.example.com
10.0.0.3 controller.example.com
10.0.0.4 master.nms.example.com
10.0.0.4 magma-test.nms.example.com
```
Here replace `example.com` with your actual domain name.


## Create admin users

### Orchestrator
The NMS requires some basic certificate-based authentication when making calls to the Orchestrator 
API. To support this, we need to add the relevant certificate as an admin user to the controller.

```bash
juju run-action orc8r-orchestrator/0 create-orchestrator-admin-user
```

### NMS
Create an admin user for the master organization on the NMS. Here specify an email and password that 
you will want to use when connecting to NMS as an admin.

```bash
ubuntu@thinkpad:~$ juju run-action nms-magmalte/0 create-nms-admin-user email=admin@example.com password=password123
```

## Verify the Deployment
### NMS 
You can confirm successful deployment by visiting the master NMS organization at e.g. 
https://master.nms.example.com and logging in with your email and password provided above 
(admin@example.com and password123 in this example). NOTE: the https:// is required. 
If you self-signed certs above, the browser will rightfully complain. 
Either ignore the browser warnings at your own risk (some versions of Chrome won't 
allow this at all), or e.g. import the root CA from above on a per-browser basis.

### Orchestrator
For interacting with the Orchestrator REST API, a good starting point is the Swagger UI available 
at https://api.example.com/swagger/v1/ui/.

### Juju
You can run `juju status` and you should see all charms are in the `Active-Idle`status.

### Kubernetes
You can run `kubectl get pods -n <your model>` and you should see that all pods are up and 
running.

## Debug
Logs can be found by querying each individual pod. Example:

```bash
ubuntu@thinkpad:~$ kubectl logs nms-magmalte-0 -c magma-nms-magmalte -n <your model> --follow
```

#### Change log verbosity
You can set the log level of any service using the `set-log-verbosity` action. The default log
level is 0 and the full log level is 10. Here is an example of setting the log level to 10 for the 
`obsidian` service:

```bash
ubuntu@thinkpad:~$ juju run-action orc8r-orchestrator/0 set-log-verbosity level=10 service=obsidian
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
