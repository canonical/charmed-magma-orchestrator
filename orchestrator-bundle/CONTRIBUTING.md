# Contributing/Hacking

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

## Build
Building and publishing charms is done using charmcraft (official documentation
[here](https://juju.is/docs/sdk/publishing)). You can install charmcraft using `snap`:

```bash
sudo snap install charmcraft --channel=edge
```

### Specific Charm

Go to the charm directory you want to build and run:

```bash
charmcraft pack
```


### Bundle

Building charms is done using [charmcraft](https://github.com/canonical/charmcraft). To install 
charmcraft:
```bash
sudo snap install charmcraft --classic
```
Initialize LXD:

```bash
lxd init --auto
```

Since multiple charms are bundled here, the process is streamlined using a simple bash script:
```bash
./build.sh
```

## Deploy

### Specific Charm

Specific charm deployment steps are documented in each of their README.md files.


### Bundle

After the packages have been built you can deploy orchestrator using juju:

```bash
juju deploy ./bundle-local.yaml --trust
```

Or you can also run the `deploy.sh` bash script (which does the exact same Juju command):

```bash
./deploy.sh
```

## Publish

### Specific Charm

First `cd` into the charm directory

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

### Bundle
To publish the bundle, `cd` to the `orc8r-bundle` directory. Pack the bundle:

```bash
charmcraft pack
```

Upload it to charmhub:

```bash
charmcraft upload magma-orc8r.zip
```

And release it:

```bash
charmcraft release magma-orc8r --revision=2 --channel=edge
```
