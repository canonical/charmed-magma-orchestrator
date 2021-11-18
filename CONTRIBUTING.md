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
