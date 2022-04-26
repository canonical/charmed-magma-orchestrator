# How-to: Deploy Magma Orchestrator on AWS with EKS

The goal of this document is to detail how to deploy Magma's Orchestrator on AWS with EKS. To do so,
we will setup EKS, bootstrap a Juju controller, deploy Magma Orchestrator and configure A
records.

### Pre-requisites

- Ubuntu 20.04 machine with internet access
- A public domain

## 1. Set up your management environment

From a Ubuntu 20.04 machine, install the following tools:

- [Juju](https://juju.is/docs/olm/installing-juju)
- [kubectl](https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/)
- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- [eksctl](https://docs.aws.amazon.com/eks/latest/userguide/eksctl.html)

Log in to your AWS account via the AWS CLI tool (instructions
[here](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-quickstart.html)).

## 2. Deploy Kubernetes on AWS using EKS

Follow this [guide](<https://juju.is/docs/olm/amazon-elastic-kubernetes-service-(amazon-eks)#heading--install-the-juju-client>) to deploy a Kubernetes cluster using EKS and bootstrap a Juju controller.

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

## 7. Verify the deployment

Confirm successful deployment by visiting `https://master.nms.<your domain>` and logging in
with the `<admin email>` and `<admin password>` provided above.
