# Contributing / Hacking

## Intended use case

The charms and bundles in this repository are specifically developed for the 
[magma](https://www.magmacore.org/) usecase.

## Roadmap

1. Charm Magma Orchestrator (microk8s)
2. Charm Magma Access Gateway with MAAS (Bare metal)
3. Charm Magma Federation Gateway (microk8s)
4. Validate public cloud deployments (AWS, GCP and Azure)

## Developing and testing
Testing for each charm is done the same way. First `cd` into the charm directory and then use 
`tox` like so:
```shell
tox -e lint      # code style
tox -e static    # static analysis
tox -e unit      # unit tests
```

tox creates virtual environment for every tox environment defined in
[tox.ini](tox.ini). Create and activate a virtualenv with the development requirements:

```bash
source .tox/unit/bin/activate
```

## Integration tests
To run the integration tests suite, run the following commands:
```bash
tox -e integration
```

## Building and publishing using charmcraft
Building and publishing charms is done using charmcraft (official documentatio
[here](https://juju.is/docs/sdk/publishing)). You can install charmcraft using `snap`:

```bash
sudo snap install charmcraft --channel=edge
```

### Build
To build your charm, `cd` into the charm directory and run:
```bash
charmcraft pack
```

### Publish

#### Register
If the charm is new and not already registered, register it:

```bash
charmcraft register magma-orc8r-<charm-name>
```

#### Upload charm
You can then upload the charm to charmhub:
```bash
charmcraft upload magma-orc8r-<charm-name>_ubuntu-20.04-amd64.charm
```

#### Upload resource
Upload the OCI image to charmhub:
```bash
charmcraft upload-resource magma-orc8r-<charm-name> magma-orc8r-<charm-name>-image --image=docker.artifactory.magmacore.org/controller@sha256:28abd1764f7a1486af533d3a6caa3bfb23033a9786df68d0374447ba75ce5fae
```

#### Release
```bash
charmcraft release magma-orc8r-<charm-name> --revision=1 --channel=edge --resource=magma-orc8r-<charm-name>-image:1
```
