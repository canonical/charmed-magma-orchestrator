# magmga-orc8r-eventd

## Description

magma-orc8r-eventd is a service that acts like an intermediary for different magma services, using the service303
interface, it will receive and push the generated registered events to the td-agent-bit service on
the gateway, so these can be then later sent to Orchestrator. These events will be sent to
ElasticSearch where they can be queried.
<br>
Visit [Magma Architecture Overview](https://docs.magmacore.org/docs/lte/architecture_overview) to 
learn more.

## Usage
**magma-orc8r-eventd** can be deployed via Juju command line using below commands:

```bash
juju deploy magma-orc8r-eventd  orc8r-eventd
```

**IMPORTANT**: For now, deploying this charm must be done with an alias as shown above.

Before running **juju deploy** command, make sure charm has been built using:
```bash
charmcraft pack
```

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.7.0
