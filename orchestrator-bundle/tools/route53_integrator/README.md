# Route53 Integrator

## Summary
Route53 is AWS's domain name service. This script aims at configuring Route53 for the correct 
Magma Orchestrator services to be accessible using domain names. The script creates a hosted Zone 
and the following A records
- `api.<your domain>`
- `bootstrapper-controller.<your domain>`
- `controller.<your domain>`
- `*.nms.<your domain>`


These A records are associated to Kubernetes LoadBalancer services that were created when deploying
the charmed-orc8r bundle:

```bash
NAME                                 TYPE           CLUSTER-IP       EXTERNAL-IP                                                              PORT(S)                                                    AGE
nginx-proxy                          LoadBalancer   10.152.183.247   aed45502648b048388bdec5bddb9a64d-490688296.us-east-1.elb.amazonaws.com   443:30760/TCP                                              24h
orc8r-bootstrap-nginx                LoadBalancer   10.152.183.29    a56ff6f8432f444edbc46f32ea281f92-213939155.us-east-1.elb.amazonaws.com   80:31200/TCP,443:30747/TCP,8444:30618/TCP                  24h
orc8r-clientcert-nginx               LoadBalancer   10.152.183.201   a93a2c577f36543f494648dba7b0ae6d-507889073.us-east-1.elb.amazonaws.com   80:31641/TCP,443:31082/TCP,8443:31811/TCP                  24h
orc8r-nginx-proxy                    LoadBalancer   10.152.183.110   aa63d9dbebba644a49f8f149e2f72c78-40891796.us-east-1.elb.amazonaws.com    80:32035/TCP,8443:30130/TCP,8444:31694/TCP,443:30794/TCP   24h
```

Note that in your cluster, the `CLUSTER-IP` and `EXTERNAL-IP` fields you'll see will be different 
from those here. 

Here is the association between the record names and Kubernetes service that will
be created by the script:


| Kubernetes service       | Record name                             | External IP*                                                              |
|:-------------------------|:----------------------------------------|:--------------------------------------------------------------------------|
| `nginx-proxy`            | `*.nms.<your domain>`                   | `aed45502648b048388bdec5bddb9a64d-490688296.us-east-1.elb.amazonaws.com`  |
| `orc8r-bootstrap-nginx`  | `bootstrapper-controller.<your domain>` | `a56ff6f8432f444edbc46f32ea281f92-213939155.us-east-1.elb.amazonaws.com ` |
| `orc8r-clientcert-nginx` | `controller.<your domain>`              | `a93a2c577f36543f494648dba7b0ae6d-507889073.us-east-1.elb.amazonaws.com`  |
| `orc8r-nginx-proxy`      | `api.<your domain>`                     | `aa63d9dbebba644a49f8f149e2f72c78-40891796.us-east-1.elb.amazonaws.com`   |

## Usage

All you need to do is install the pip libraries located in the `requirements.txt` file and run the 
script using a Python3 interpreter.

```bash
pip3 install -r requirements.txt
python3 main.py --hosted_zone=<hosted_zone> --namespace <kubernetes namespace>
```

Replace `<hosted_zone>` with your domain name and `<kubernetes namespace>` with your Juju model name.
