# How-to: Deploy Magma Orchestrator on AWS with Charmed Kubernetes

The goal of this document is to detail how to deploy Magma's Orchestrator on AWS with Charmed
Kubernetes. You will deploy charmed Kubernetes, bootstrap a Juju controller, deploy Magma Orchestrator and configure A
records.

### Pre-requisites

- Ubuntu 20.04 machine with internet access
- A public domain

## 1. Set up your management environment

From a Ubuntu 20.04 machine, install the following tools:

- [Juju](https://juju.is/docs/olm/installing-juju)
- [kubectl](https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/)
- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)

Log in to your AWS account via the AWS CLI tool (instructions
[here](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-quickstart.html)).

## 2. Deploy Charmed Kubernetes on AWS using Juju

From your Ubuntu machine, bootstrap an AWS Juju controller:

```bash
juju bootstrap aws <your aws region> <juju AWS controller name>
```

Create an `overlay.yaml` file that contains the following content:

```yaml
description: Charmed Kubernetes overlay to add native AWS support.
applications:
  aws-integrator:
    charm: cs:~containers/aws-integrator
    num_units: 1
    trust: true
relations:
  - ['aws-integrator', 'kubernetes-master']
  - ['aws-integrator', 'kubernetes-worker']
```

Deploy charmed-kubernetes:

```bash
juju deploy charmed-kubernetes --overlay overlay.yaml --trust
```

The deployment is completed when all services are in the `Active-Idle` state.

Fetch the kubectl config file:

```bash
juju scp kubernetes-master/0:config ~/.kube/config
```

To test communication with the Kubernetes cluster, run:

```bash
kubectl get nodes
```

Add this new k8s endpoint and credentials to Juju:

```bash
juju add-k8s <controller name>
```

Replace `<controller name>` with the name you want for the Juju controller.

Bootstrap the new Kubernetes controller:

```bash
juju bootstrap <controller name>
```

Create a new model (namespace):

```bash
juju add-model <model name>
```

Replace `<model name>` with the Kubernetes namespace you want.

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

## 4. Import the HTTPS Certificate

Retrieve the self-signed certificate:

```bash
juju scp orc8r-certifier/0:/tmp/certs/admin_operator.pfx admin_operator.pfx
```

The default password is `password123`.

> **_NOTE:_** The default password can be changed by deploying the certifier charm using
> the Juju config `passphrase`.

## 5. Setup Orchestrator

Create the Orchestrator admin user:

```bash
juju run-action orc8r-orchestrator/0 create-orchestrator-admin-user
```

Create an admin user for the master organization on the NMS:

```bash
juju run-action nms-magmalte/0 create-nms-admin-user email=<admin email> password=<admin password>
```

Replace `<admin email>` and `<admin password>` with your email and password of choice.

## 6. Setup DNS

To configure Route53, on your Ubuntu machine clone the `charmed-magma` project:

```bash
git clone https://github.com/canonical/charmed-magma.git
```

Navigate to the `route53_integrator` directory and run the main script:

```bash
cd charmed-magma/orchestrator-bundle/tools/route53_integrator
pip3 install -r requirements.txt
python3 main.py --hosted_zone=<your domain> --namespace <your model>
```

Configure DNS records on your managed domain name to use the Route53 nameservers outputted by the
script.

> **_NOTE:_** For Google domains, navigate to Google Domains -> DNS -> Custom Name Servers. Fill in 4 Name Server
> boxes with the domains retrieved from the `route53_integrator` script.

## 7. Verify the deployment

Confirm successful deployment by visiting `https://master.nms.<your domain>` and logging in
with the `<admin email>` and `<admin password>` provided above.
