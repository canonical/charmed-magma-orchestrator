# How-to: Integrate Magma Orchestrator with elasticsearch

As of today, elasticsearch is not deployed using `juju deploy magma-orc8r`. Here we go through 
the process of deploying elasticsearch using Helm and relating orchestrator to it.

> NOTE: Relating orchestrator to elasticsearch will be modelled through a relationship once there 
> is a charm for elasticsearch running properly on public cloud environments.

### Pre-requisites

- Ubuntu 20.04 machine with internet access
- A running Magma Orchestrator instance
- A Kubernetes cluster running on public cloud


## Deploy Elasticsearch

You can use any publicly accessible elasticsearch cluster. Here we create our own using
helm. We deploy it in a public cloud environment to simplify the process of making it publicly
accessible.

```bash
kubectl create namespace elastic
helm repo add elastic https://helm.elastic.co
helm install elasticsearch elastic/elasticsearch --set service.type=LoadBalancer -n elastic
```

Once elasticsearch is up and running, retrieve its publicly accessible (external IP) LoadBalancer
address. Make sure this IP on port 9200 is accessible from your Magma orchestrator environment.

## Relate orchestrator to elasticsearch

```bash
juju config orc8r-eventd elasticsearch-url=<elasticsearch LoadBalancer IP>:9200
juju config orc8r-orchestrator elasticsearch-url=<elasticsearch LoadBalancer IP>:9200
```
