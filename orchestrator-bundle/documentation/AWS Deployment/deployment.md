
# AWS Deployment

## Summary

The goal of this document is to detail how to deploy Magma's Orchestrator component on AWS.
Here are all the items covered:

1. Register a domain
2. Deploy Kubernetes on AWS using Juju
   1. Bootstrap an AWS Juju Controller 
   2. Deploy charmed-kubernetes
   3. Bootstrap a Kubernetes Juju controller
3. Deploy charmed magma orchestrator
4. Import the HTTPS certificate
5. Setup Orchestrator
   1. Create an Orchestrator Admin User
   2. Create an NMS Admin User
6. DNS Resolution
   1. Configure Route53
   2. Configure DNS records
7. Verify the deployment

## 1. Register a domain

Orchestrator is a web service, which means you will need a domain. You can either use one that you
already own or purchase one via your domain registrar of choice. In this example we will use a 
domain purchased from Google Domains and refer to it as `<your domain>`.

## 2. Deploy Kubernetes on AWS using Juju

### Pre-requisites

You will need access to a Ubuntu 20.04 machine. On this machine, make sure you have the 
following software installed:
- [Juju](https://juju.is/docs/olm/installing-juju)
- [kubectl](https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/)
- [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)

You will also need an AWS account. From your Ubuntu machine, you will need to be logged in 
to your account via the AWS CLI tool (instructions 
[here](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-quickstart.html)).

![Alt text](images/pre_requisites.png?raw=true "Title")

### i. Bootstrap an AWS Juju controller
From your Ubuntu machine, first bootstrap an AWS Juju controller:

```bash
juju bootstrap aws <your aws region> <juju AWS controller name>
```

This will have created an EC2 instance called `juju-controller-machine-0`. 

![Alt text](images/bootstrap_aws_controller.png?raw=true "Title")

### ii. Deploy charmed Kubernetes

We will now deploy a Kubernetes cluster on AWS EC2 instances with the `charmed-kubernetes` Juju 
charms. Charmed Kubernetes is a set of charms that works on multiple clouds (AWS, Azure, GCP) and 
the differentiation between clouds is done using an integrator charm. In our case, it's the 
`aws-integrator-charm` that will be specified in an overlay file. Create an `overlay.yaml` file 
that contains the following content:

```yaml
description: Charmed Kubernetes overlay to add native AWS support.
applications:
  aws-integrator:
    annotations:
      gui-x: "600"
      gui-y: "300"
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
Deploying charmed-kubernetes can take a while, you can follow the progress using `juju status`. 
Once the deployment is complete, fetch the kubectl config file:

```bash
juju scp kubernetes-master/0:config ~/.kube/config
```

You should now be able to communicate with this cluster via `kubectl` commands. To test this, you can
run:

```bash
kubectl get pods --all-namespaces
```

![Alt text](images/deploy_charmed_k8s.png?raw=true "Title")


### iii. Bootstrap a Kubernetes Juju controller
First add this new k8s endpoint and credential to Juju:

```bash
juju add-k8s <controller name>
```

`<controller name>` is the name that will be given to your new Kubernetes juju controller. 
Now bootstrap the new Kubernetes controller:

```bash
juju bootstrap <controller name>
```

Create a new model (namespace)

```bash
juju add-model <model name>
```

`<model name>` can be any name you want. This model will be the actual Kubernetes namespace.

![Alt text](images/bootstrap_k8s_controller.png?raw=true "Title")


### Validation
At this point we have 2 Juju controller:
- AWS Controller
- Kubernetes Controller

You can validate this by running 

```bash
juju list-controllers
```

The output should look like this:

```bash
Controller             Model                  User   Access     Cloud/Region           Models  Nodes    HA    Version
aws-<your aws region>  default                admin  superuser  aws/<your aws region>  2       15       none  2.9.22  
<controller name>*     <model name>           admin  superuser  <controller name>      2        -       -     2.9.22  
```

Note that you can switch between the two controllers using `juju switch <controller name>`.

## 3. Deploy charmed magma orchestrator

Deploy orchestrator using `juju deploy`:

```bash
juju deploy postgresql-k8s
juju deploy magma-orc8r-certifier orc8r-certifier \
 --config domain=<your domain> \
 --channel=edge \
 --trust
juju deploy magma-orc8r-obsidian orc8r-obsidian --channel=edge --trust
juju deploy magma-orc8r-bootstrapper orc8r-bootstrapper --channel=edge --trust
juju deploy magma-orc8r-nginx orc8r-nginx --channel=edge --trust
juju deploy magma-nms-magmalte nms-magmalte --channel=edge --trust
juju deploy magma-nms-nginx-proxy nms-nginx-proxy --channel=edge --trust
juju deploy magma-orc8r-service-registry orc8r-service-registry --channel=edge --trust
juju deploy magma-orc8r-orchestrator orc8r-orchestrator --channel=edge --trust
juju deploy magma-orc8r-accessd orc8r-accessd --channel=edge --trust
juju deploy magma-orc8r-configurator orc8r-configurator --channel=edge --trust
juju deploy magma-orc8r-lte orc8r-lte --channel=edge --trust
juju deploy magma-orc8r-directoryd orc8r-directoryd --channel=edge --trust
juju deploy magma-orc8r-dispatcher orc8r-dispatcher --channel=edge --trust
juju deploy magma-orc8r-ctraced orc8r-ctraced --channel=edge --trust
juju deploy magma-orc8r-device orc8r-device --channel=edge --trust
juju deploy magma-orc8r-eventd orc8r-eventd --channel=edge --trust
juju deploy magma-orc8r-ha orc8r-ha --channel=edge --trust
juju deploy magma-orc8r-metricsd orc8r-metricsd --channel=edge --trust
juju deploy magma-orc8r-policydb orc8r-policydb --channel=edge --trust
juju deploy magma-orc8r-smsd orc8r-smsd --channel=edge --trust
juju deploy magma-orc8r-state orc8r-state --channel=edge --trust
juju deploy magma-orc8r-streamer orc8r-streamer --channel=edge --trust
juju deploy magma-orc8r-subscriberdb-cache orc8r-subscriberdb-cache --channel=edge --trust
juju deploy magma-orc8r-subscriberdb orc8r-subscriberdb --channel=edge --trust
juju deploy magma-orc8r-tenants orc8r-tenants --channel=edge --trust
juju deploy prometheus-k8s orc8r-prometheus --channel=edge --trust
juju deploy prometheus-edge-hub prometheus-cache --channel=edge --trust

juju relate orc8r-bootstrapper orc8r-certifier
juju relate orc8r-certifier postgresql-k8s:db
juju relate orc8r-nginx:certifier orc8r-certifier:certifier
juju relate orc8r-nginx:bootstrapper orc8r-bootstrapper:bootstrapper
juju relate orc8r-nginx:obsidian orc8r-obsidian:obsidian
juju relate nms-magmalte postgresql-k8s:db
juju relate nms-magmalte orc8r-certifier
juju relate nms-nginx-proxy orc8r-certifier
juju relate nms-nginx-proxy nms-magmalte
juju relate orc8r-orchestrator orc8r-certifier
juju relate orc8r-accessd postgresql-k8s:db
juju relate orc8r-configurator postgresql-k8s:db
juju relate orc8r-lte postgresql-k8s:db
juju relate orc8r-directoryd postgresql-k8s:db
juju relate orc8r-ctraced postgresql-k8s:db
juju relate orc8r-device postgresql-k8s:db
juju relate orc8r-smsd postgresql-k8s:db
juju relate orc8r-policydb postgresql-k8s:db
juju relate orc8r-state postgresql-k8s:db
juju relate orc8r-tenants postgresql-k8s:db
juju relate orc8r-subscriberdb-cache postgresql-k8s:db
juju relate orc8r-subscriberdb postgresql-k8s:db
juju relate orc8r-prometheus prometheus-cache
```

> **NOTE**: In the future there will be a bundle to deploy magma orchestrator via a one line command
> but there is a current bug preventing this.

You can look at the deployment status using `juju status`. The deployment is completed when
all services are in the `Active-Idle` state:

```bash
Model         Controller            Cloud/Region        Version  SLA          Timestamp
<your model>   <controller name>    <controller name>   2.9.22   unsupported  07:40:52-05:00

App                       Version                 Status  Scale  Charm                           Store     Channel  Rev  OS          Address         Message
nms-magmalte                                      active      1  magma-nms-magmalte              charmhub  edge       5  kubernetes                  
nms-nginx-proxy                                   active      1  magma-nms-nginx-proxy           charmhub  edge       2  kubernetes                  
orc8r-accessd                                     active      1  magma-orc8r-accessd             charmhub  edge       7  kubernetes  10.152.183.176  
orc8r-bootstrapper                                active      1  magma-orc8r-bootstrapper        charmhub  edge       2  kubernetes  10.152.183.244  
orc8r-certifier                                   active      1  magma-orc8r-certifier           charmhub  edge       4  kubernetes  10.152.183.138  
orc8r-configurator                                active      1  magma-orc8r-configurator        charmhub  edge       2  kubernetes  10.152.183.218  
orc8r-ctraced                                     active      1  magma-orc8r-ctraced             charmhub  edge       2  kubernetes  10.152.183.199  
orc8r-device                                      active      1  magma-orc8r-device              charmhub  edge       3  kubernetes  10.152.183.19   
orc8r-directoryd                                  active      1  magma-orc8r-directoryd          charmhub  edge       3  kubernetes  10.152.183.233  
orc8r-dispatcher                                  active      1  magma-orc8r-dispatcher          charmhub  edge       3  kubernetes  10.152.183.25   
orc8r-eventd                                      active      1  magma-orc8r-eventd              charmhub  edge       3  kubernetes  10.152.183.161  
orc8r-ha                                          active      1  magma-orc8r-ha                  charmhub  edge       3  kubernetes  10.152.183.178  
orc8r-lte                                         active      1  magma-orc8r-lte                 charmhub  edge       2  kubernetes  10.152.183.242  
orc8r-metricsd                                    active      1  magma-orc8r-metricsd            charmhub  edge       2  kubernetes  10.152.183.102  
orc8r-nginx                                       active      1  magma-orc8r-nginx               charmhub  edge       2  kubernetes  10.152.183.177  
orc8r-obsidian                                    active      1  magma-orc8r-obsidian            charmhub  edge       2  kubernetes  10.152.183.96   
orc8r-orchestrator                                active      1  magma-orc8r-orchestrator        charmhub  edge       2  kubernetes  10.152.183.143  
orc8r-policydb                                    active      1  magma-orc8r-policydb            charmhub  edge       2  kubernetes  10.152.183.195  
orc8r-prometheus                                  active      1  prometheus-k8s                  charmhub  edge      19  kubernetes  10.152.183.13   
orc8r-service-registry                            active      1  magma-orc8r-service-registry    charmhub  edge       3  kubernetes  10.152.183.110  
orc8r-smsd                                        active      1  magma-orc8r-smsd                charmhub  edge       2  kubernetes  10.152.183.18   
orc8r-state                                       active      1  magma-orc8r-state               charmhub  edge       2  kubernetes  10.152.183.55   
orc8r-streamer                                    active      1  magma-orc8r-streamer            charmhub  edge       2  kubernetes  10.152.183.83   
orc8r-subscriberdb                                active      1  magma-orc8r-subscriberdb        charmhub  edge       2  kubernetes  10.152.183.77   
orc8r-subscriberdb-cache                          active      1  magma-orc8r-subscriberdb-cache  charmhub  edge       2  kubernetes  10.152.183.249  
orc8r-tenants                                     active      1  magma-orc8r-tenants             charmhub  edge       2  kubernetes  10.152.183.42   
postgresql-k8s            .../postgresql@ed0e37f  active      1  postgresql-k8s                  charmhub  stable     3  kubernetes  10.152.183.239  
prometheus-cache                                  active      1  prometheus-edge-hub             charmhub  edge       2  kubernetes  10.152.183.171  

Unit                         Workload  Agent  Address     Ports     Message
nms-magmalte/0*              active    idle   10.1.89.34            
nms-nginx-proxy/0*           active    idle   10.1.35.42            
orc8r-accessd/0*             active    idle   10.1.55.9             
orc8r-bootstrapper/0*        active    idle   10.1.35.40            
orc8r-certifier/0*           active    idle   10.1.35.35            
orc8r-configurator/0*        active    idle   10.1.35.38            
orc8r-ctraced/0*             active    idle   10.1.89.33            
orc8r-device/0*              active    idle   10.1.55.11            
orc8r-directoryd/0*          active    idle   10.1.55.10            
orc8r-dispatcher/0*          active    idle   10.1.35.39            
orc8r-eventd/0*              active    idle   10.1.35.43            
orc8r-ha/0*                  active    idle   10.1.89.36            
orc8r-lte/0*                 active    idle   10.1.89.32            
orc8r-metricsd/0*            active    idle   10.1.89.37            
orc8r-nginx/0*               active    idle   10.1.35.41            
orc8r-obsidian/0*            active    idle   10.1.89.28            
orc8r-orchestrator/0*        active    idle   10.1.89.35            
orc8r-policydb/0*            active    idle   10.1.55.12            
orc8r-prometheus/0*          active    idle   10.1.89.40            
orc8r-service-registry/0*    active    idle   10.1.35.37            
orc8r-smsd/0*                active    idle   10.1.89.38            
orc8r-state/0*               active    idle   10.1.55.13            
orc8r-streamer/0*            active    idle   10.1.35.44            
orc8r-subscriberdb-cache/0*  active    idle   10.1.55.14            
orc8r-subscriberdb/0*        active    idle   10.1.55.15            
orc8r-tenants/0*             active    idle   10.1.35.45            
postgresql-k8s/0*            active    idle   10.1.35.36  5432/TCP  Pod configured
prometheus-cache/0*          active    idle   10.1.89.39            
```

## 4. Import the HTTPS Certificate
In this example we are using self-signed certificates. This means that You will need to import a 
certificate in your browser for it to trust traffic coming from Orchestrator. First retrieve the 
certificate that was generated by the `orc8r-certifier` service:

```bash
juju scp orc8r-certifier/0:/tmp/certs/admin_operator.pfx admin_operator.pfx
```

Then import this file in your browser. For Chrome, this is done by navigating here: 
Settings -> Security and Privacy -> Manage Certificates -> Your Certificates -> Import. You 
will be asked for the certificate's password, which is `password123`. This password can be changed 
by deploying the certifier charm using the Juju config `passphrase`.

## 5. Setup Orchestrator

### i. Create an Orchestrator Admin User

The NMS requires some basic certificate-based authentication when making calls to the Orchestrator 
API. To support this, we need to add the relevant certificate as an admin user to the controller.

```bash
juju run-action orc8r-orchestrator/0 create-orchestrator-admin-user
```

### ii. Create an NMS Admin User
Create an admin user for the master organization on the NMS:

```bash
juju run-action nms-magmalte/0 create-nms-admin-user email=<admin email> password=<admin password>
```

Replace `<admin email>` and `<admin password>` with your email and password of choice.

## 6. DNS Resolution

### i. Configure Route53

Route53 is a AWS's domain name service. We will use it to create A records for the following 4 
subdomains:
- `api.<your domain>`
- `bootstrapper-controller.<your domain>`
- `controller.<your domain>`
- `*.nms.<your domain>`

First we need to create a hosted zone for our domain. Navigate to Route53 -> Hosted Zones -> 
Create Hosted Zone. Write down your domain name and click **Create Hosted Zone**.

These 4 subdomains will need to be associated to 4 LoadBalancer services that were just created. 
Retrieve them using `kubectl`:

```bash
$ kubectl get services -n <your model> | grep LoadBalancer
NAME                                 TYPE           CLUSTER-IP       EXTERNAL-IP                                                              PORT(S)                                                    AGE
nginx-proxy                          LoadBalancer   10.152.183.247   aed45502648b048388bdec5bddb9a64d-490688296.us-east-1.elb.amazonaws.com   443:30760/TCP                                              24h
orc8r-bootstrap-nginx                LoadBalancer   10.152.183.29    a56ff6f8432f444edbc46f32ea281f92-213939155.us-east-1.elb.amazonaws.com   80:31200/TCP,443:30747/TCP,8444:30618/TCP                  24h
orc8r-clientcert-nginx               LoadBalancer   10.152.183.201   a93a2c577f36543f494648dba7b0ae6d-507889073.us-east-1.elb.amazonaws.com   80:31641/TCP,443:31082/TCP,8443:31811/TCP                  24h
orc8r-nginx-proxy                    LoadBalancer   10.152.183.110   aa63d9dbebba644a49f8f149e2f72c78-40891796.us-east-1.elb.amazonaws.com    80:32035/TCP,8443:30130/TCP,8444:31694/TCP,443:30794/TCP   24h
```

Obviously the cluster IP's and  external IP's you'll see will be different from mine.

Here is the association between the record names and Kubernetes service that we will need to create.

| Record Name                             | Kubernetes service       |
|:----------------------------------------|:-------------------------|
| `api.<your domain>`                     | `orc8r-nginx-proxy`      |
| `bootstrapper-controller.<your domain>` | `orc8r-bootstrap-nginx`  |
| `controller.<your domain>`              | `orc8r-clientcert-nginx` |
| `*.nms.<your domain>`                   | `nginx-proxy`            |

Let's created those A records in route53. Navigate to Route53 -> Hosted Zones -> `<your domain` 
and click on **Create record**.
- Record name: `api.<your domain>`
- Record type: A
- Routing policy: Simple routing
- Alias: Yes
- Route traffic to: Alias to Application and Classic Load Balancer
- Choose Region: `<your aws regions>`
- Value: `aa63d9dbebba644a49f8f149e2f72c78-40891796.us-east-1.elb.amazonaws.com`

Here the value you will enter will be different from mine depending on the LoadBalancer's external
address associated to your `oc8r-nginx-proxy` service. Next do the same for the other 3
subdomains.


### ii. Configure DNS records

You will need to configure your DNS records on your managed domain name to use the Route53 
nameservers in order to resolve these subdomains. Navigate to Route53 -> Hosted Zones -> 
`<your domain>` and note the values associated to your domain's NS record. You should have 4 values
that look something like:
- `ns-1703.awsdns-20.co.uk`
- `ns-1233.awsdns-26.org`
- `ns-509.awsdns-63.com`
- `ns-516.awsdns-00.net`

In this example, our domain is registered with Google Domains. To configure our DNS records, 
head to Google Domains ->DNS -> Custom Name Servers. Fill in 4 Name Server boxes with the domains 
retrieved from route53. Make sure that your domain is using these settings. If it isn't, you will
be prompted with a warning telling you "Your domain isn't using these settings". If that's the 
case click on **Switch to these settings**.

## 7. Verify the deployment

After a few minutes the NS records should propagate. Confirm successful deployment by visiting the 
master NMS organization at e.g. `https://master.nms.<your domain>` and logging in 
with the `<admin email>` and `<admin password>` provided above.

For interacting with the Orchestrator REST API, a good starting point is the Swagger UI available 
at `https://api.<your domain>/swagger/v1/ui/`.

If desired, you can also visit the AWS endpoints directly. The relevant services are nginx-proxy 
for NMS and orc8r-nginx-proxy for Orchestrator API. Remember to include https://, as well as the 
port number for non-standard TLS ports.
