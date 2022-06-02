# magma-orc8r-nginx

## Description

magma-orc8r-nginx facilitates communication between NMS and Orchestrator Application. Visit 
[Magma Architecture Overview](https://docs.magmacore.org/docs/orc8r/architecture_overview) 
to learn more.

This [Juju](https://juju.is/) Charm deploys an **nginx** web server that proxies communication
between NMS and Orchestrator Application.<br>
This charm is part of the [Charmed Magma bundle](https://github.com/canonical/charmed-magma).

## Usage

**magma-orc8r-nginx** can be deployed via Juju command line using below commands:

```bash
juju deploy magma-orc8r-nginx orc8r-nginx --config domain=<your domain>
juju deploy magma-orc8r-bootstrapper orc8r-bootstrapper
juju deploy magma-orc8r-obsidian orc8r-obsidian
juju relate orc8r-nginx:bootstrapper orc8r-bootstrapper:bootstrapper
juju relate orc8r-nginx:obsidian orc8r-obsidian:obsidian
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

## Config
One config is mandatory:
- domain: Orchestrator domain name

## Relations

### Provides

This charm provides no relation.

### Requires

The following relations are required:

- [magma-orc8r-bootstrapper](https://github.com/canonical/charmed-magma/tree/main/orchestrator-bundle/orc8r-bootstrapper-operator) -
  magma-orc8r-bootstrapper manages the certificate bootstrapping process for newly registered gateways 
  and gateways whose cert has expired.
- [magma-orc8r-obsidian](https://github.com/canonical/charmed-magma/tree/main/orchestrator-bundle/orc8r-obsidian-operator) -
  magma-orc8r-obsidian verifies API request access control and reverse proxies requests to Orchestrator 
  services with the appropriate API handlers.


## OCI Images

Default: nginx:latest
