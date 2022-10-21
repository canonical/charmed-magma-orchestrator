# Contributing/Hacking

## Developing and testing
Testing is done using `tox`:

```shell
tox -e lint      # code style
tox -e static    # static analysis
tox -e unit      # unit tests
```

## Publishing

### Orc8r Base
```bash
charmcraft publish-lib charms.magma_orc8r_libs.v0.orc8r_base
```

### Orc8r Base DB
```bash
charmcraft publish-lib charms.magma_orc8r_libs.v0.orc8r_base_db
```
