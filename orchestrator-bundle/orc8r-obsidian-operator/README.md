# orc8r-obsidian

## Description
obsidian verifies API request access control and reverse proxies requests to Orchestrator services with the appropriate API handlers.

## Usage

```bash
juju deploy ./magma-orc8r-obsidian_ubuntu-20.04-amd64.charm \
  --resource magma-orc8r-obsidian-image=docker.artifactory.magmacore.org/controller:1.6.0
```

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0

## Contributing

Please see `CONTRIBUTING.md` for developer guidance.
