# magmga-orc8r-eventd

## Description

Service that acts like an intermediary for different magma services, using the service303
interface, it will receive and push the generated registered events to the td-agent-bit service on
the gateway, so these can be then later sent to Orchestrator. These events will be sent to
ElasticSearch where they can be queried.
<br>
Visit [Magma Architecture Overview](https://docs.magmacore.org/docs/lte/architecture_overview) to 
learn more.

## Usage
**magma-orc8r-eventd** can be deployed via Juju command line using below commands:

```bash
juju deploy ./magma-orc8r-eventd_ubuntu-20.04-amd64.charm \
  --resource magma-orc8r-eventd-image=docker.artifactory.magmacore.org/controller:1.6.0 \
  orc8r-eventd
```

Before running **juju deploy** command, make sure charm has been built using:
```bash
charmcraft pack
```

## Relations

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0

## Contributing

Please see `CONTRIBUTING.md` for developer guidance.
