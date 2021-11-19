# orc8r-service-registry

## Description
service_registry provides service discovery for all services in the Orchestrator by querying Kubernetes's API server

## Usage

```bash
juju deploy ./magma-orc8r-service-registry_ubuntu-20.04-amd64.charm \
  --resource magma-orc8r-service-registry-image=docker.artifactory.magmacore.org/controller:1.6.0
```

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0

## Contributing

Please see `CONTRIBUTING.md` for developer guidance.
