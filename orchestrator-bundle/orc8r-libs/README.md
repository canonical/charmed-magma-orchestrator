# magma-orc8r-libs

## Description

magma-orc8r-libs is a placeholder charm that contains libraries used for magma orc8r. Most orc8r charms
are very similar and this library makes it possible to avoid code duplication between the charms.

## Usage
While it is possible to deploy this charm, it is essentially a no-op, and not what this charm was 
designed for.

Where this charm should be used, is to access one of the following libraries during development:
- Orc8rBase: Base charm for all of orc8r charms that don't require database connectivity.
- Orc8rBaseDB: Base charm for all of orc8r charms that require database connectivity.

To get started using the library, you just need to fetch the library using `charmcraft`.

### Orc8r Base
```shell
cd some-charm
charmcraft fetch-lib charms.magma_orc8r_libs.v0.orc8r_base
```

### Orc8r Base DB
```shell
cd some-charm
charmcraft fetch-lib charms.magma_orc8r_libs.v0.orc8r_base_db
```
