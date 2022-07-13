# magma-orc8r-nginx

## Description

magma-orc8r-nginx facilitates communication between NMS and Orchestrator Application. Visit 
[Magma Architecture Overview](https://docs.magmacore.org/docs/orc8r/architecture_overview) 
to learn more.

This [Juju](https://juju.is/) Charm deploys an **nginx** web server that proxies communication
between NMS and Orchestrator Application.<br>
This charm is part of the [Charmed Magma bundle](https://github.com/canonical/charmed-magma).

## Usage


```bash
juju deploy magma-orc8r-nginx orc8r-nginx --trust --config domain=<your domain>
juju relate orc8r-nginx orc8r-bootstrapper
juju relate orc8r-nginx orc8r-obsidian
juju relate orc8r-nginx:cert-certifier orc8r-certifier:cert-certifier
juju relate orc8r-nginx:cert-controller orc8r-certifier:cert-controller
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

## Relations

Currently supported relations are:

- [magma-orc8r-certifier](https://github.com/canonical/charmed-magma/tree/main/orchestrator-bundle/orc8r-certifier-operator) - 
  magma-orc8r-certifier maintains and verifies signed client certificates and their associated
  identities.
- [magma-orc8r-bootstrapper](https://github.com/canonical/charmed-magma/tree/main/orchestrator-bundle/orc8r-bootstrapper-operator) -
  magma-orc8r-bootstrapper manages the certificate bootstrapping process for newly registered gateways 
  and gateways whose cert has expired.
- [magma-orc8r-obsidian](https://github.com/canonical/charmed-magma/tree/main/orchestrator-bundle/orc8r-obsidian-operator) -
  magma-orc8r-obsidian verifies API request access control and reverse proxies requests to Orchestrator 
  services with the appropriate API handlers.


## OCI Images

Default: nginx:latest
