# Contributing/Hacking

## Developing and testing

Testing for each charm is done the same way. First `cd` into the charm directory and then use 
`tox` like so:
```shell
tox -e lint      # code style
tox -e static    # static analysis
tox -e unit      # unit tests
```

**NOTE:** If you don't have `tox` installed yet, just run: `pip3 install tox`.

Tox creates virtual environment for every tox environment defined in
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
sudo snap install charmcraft --channel=classic
```

Initialize LXD:

```bash
lxd init --auto
```

### Specific Charm

Go to the charm directory you want to build and run:

```bash
charmcraft pack
```


### Bundle


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
