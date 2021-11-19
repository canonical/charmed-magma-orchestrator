# orc8r-nginx

## Description

magma-orc8r-nginx facilitates communication between NMS and Orchestrator Application. Visit 
[Magma Architecture Overview](https://docs.magmacore.org/docs/orc8r/architecture_overview) 
to learn more.

This [Juju](https://juju.is/) Charm deploys an **nginx** web server that proxies communication
between NMS and Orchestrator Application.<br>
This charm is part of the [Charmed Magma bundle](https://github.com/canonical/magma-orc8r-dev).

## Usage

**magma-orc8r-nginx** can be deployed via Juju command line using below commands:

```bash
juju deploy ./magma-orc8r-nginx_ubuntu-20.04-amd64.charm \
  --resource magma-orc8r-nginx-image=docker.artifactory.magmacore.org/nginx:1.6.0
```

To work correctly, **magma-orc8r-nginx** requires **magma-orc8r-certifier**, 
**magma-orc8r-bootstrapper** and **magma-orc8r-obsidian** (for details, check the _Relations_ section 
below).

To deploy **magma-orc8r-certifier** from Juju command line:

```bash
juju deploy ../orc8r-certifier-operator/magma-orc8r-certifier_ubuntu-20.04-amd64.charm \
  --resource magma-orc8r-certifier-image=docker.artifactory.magmacore.org/controller:1.6.0 \
  --config domain=example.com
juju relate magma-orc8r-nginx:certifier magma-orc8r-certifier:certifier
```

To deploy **magma-orc8r-bootstrapper** from Juju command line:

```bash
juju deploy ../orc8r-bootstrapper-operator/magma-orc8r-bootstrapper_ubuntu-20.04-amd64.charm \
  --resource magma-orc8r-bootstrapper-image=docker.artifactory.magmacore.org/controller:1.6.0
juju relate magma-orc8r-nginx:magma-orc8r-bootstrapper magma-orc8r-bootstrapper:magma-orc8r-bootstrapper
```

To deploy **magma-orc8r-obsidian** from Juju command line:

```bash
juju deploy ../magma-orc8r-obsidian/magma-orc8r-obsidian_ubuntu-20.04-amd64.charm \
  --resource magma-orc8r-obsidian-image=docker.artifactory.magmacore.org/controller:1.6.0
juju relate magma-orc8r-nginx:obsidian magma-orc8r-obsidian:obsidian
```

Before running any **juju deploy** commands, make sure charm has been built using:
```bash
charmcraft pack
```

## Relations

Currently supported relations are:

- [magma-orc8r-certifier](https://github.com/canonical/magma-orc8r-dev/tree/main/magma-orc8r-certifier) - 
  magma-orc8r-certifier maintains and verifies signed client certificates and their associated
  identities.
- [magma-orc8r-bootstrapper](https://github.com/canonical/magma-orc8r-dev/tree/main/magma-orc8r-bootstrapper) -
  magma-orc8r-bootstrapper manages the certificate bootstrapping process for newly registered gateways 
  and gateways whose cert has expired.
- [magma-orc8r-obsidian](https://github.com/canonical/magma-orc8r-dev/tree/main/magma-orc8r-obsidian) -
  magma-orc8r-obsidian verifies API request access control and reverse proxies requests to Orchestrator 
  services with the appropriate API handlers.


## OCI Images

Default: nginx:latest

## Contributing

Please see `CONTRIBUTING.md` for developer guidance.
