# magma-orc8r-nginx

## Description

magma-orc8r-nginx deploys an **nginx** web server that proxies communication between NMS and
Orchestrator. Visit [Magma Architecture Overview](https://docs.magmacore.org/docs/orc8r/architecture_overview) to
learn more.

This charm is part of [Charmed Magma Orchestrator](https://charmhub.io/magma-orc8r/) and should
be deployed as a bundle.

## Usage

```bash
juju deploy magma-orc8r-nginx orc8r-nginx --trust --config domain=<your domain>
juju deploy magma-orc8r-certifier orc8r-certifier --config domain=<your domain>
juju deploy magma-orc8r-bootstrapper orc8r-bootstrapper
juju deploy magma-orc8r-obsidian orc8r-obsidian
juju relate orc8r-nginx orc8r-bootstrapper
juju relate orc8r-nginx orc8r-obsidian
juju relate orc8r-nginx:cert-certifier orc8r-certifier:cert-certifier
juju relate orc8r-nginx:cert-controller orc8r-certifier:cert-controller
```

> **Warning**: Deploying this charm must be done with an alias as shown above.

## Relations

### Requires

- **magma-orc8r-bootstrapper**: Used to retrieve the workload service status.
- **magma-orc8r-obsidian**: Used to retrieve the workload service status.
- **cert-controller**: Relation that provides the controller certificates.
- **cert-certifier**: Relation that provides the certifier certificates.

## OCI Images

Default: ghcr.io/canonical/nginx:1.23.3
