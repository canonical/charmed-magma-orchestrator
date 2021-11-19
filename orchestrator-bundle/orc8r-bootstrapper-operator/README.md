# orc8r-bootstrapper

## Description

 magma-orc8r-bootstrapper manages the certificate bootstrapping process for newly registered gateways and gateways whose cert has expired

## Usage

```
juju deploy ./magma-orc8r-bootstrapper_ubuntu-20.04-amd64.charm \
  --resource magma-orc8r-bootstrapper-image=docker.artifactory.magmacore.org/controller:1.6.0
juju relate magma-orc8r-bootstrapper orc8r-certifier
```

## OCI Images

Default: docker.artifactory.magmacore.org/controller:1.6.0

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines 
on enhancements to this charm following best practice guidelines, and
`CONTRIBUTING.md` for developer guidance.
