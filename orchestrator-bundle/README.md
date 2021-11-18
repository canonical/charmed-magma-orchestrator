# Magma Orchestrator

## Summary

This current project contains a set of Juju charms with the purpose of driving the lifecycle 
management, configuration, integration and daily actions for Magma's **orchestrator** component.

## Hardware requirements
- CPU: 8 vCPU's
- Memory: 32 GB
- Storage: 100 GB

## Installation Guide
This bundle of charms requires a virtual machine running Ubuntu 20.04, a microk8s cluster and Juju.

### Ubuntu
For installing Ubuntu, please follow the [official documentation](https://releases.ubuntu.com/20.04/).

### Microk8s
On your Ubuntu VM, install microk8s using snap:

```bash
sudo snap install microk8s --classic
```
Update your user's permission to be added to the microk8s group

```bash
sudo usermod -a -G microk8s ubuntu
sudo chown -f -R ubuntu ~/.kube
```
After changing those permissions, you'll have to create a new shell for them to take effect, so 
you can exit and re-ssh to the machine. Once you're in again, enable some add ons to your microk8s
cluster:

```bash
microk8s enable ingress dns storage
```

### Juju
Install Juju using snap:

```bash
sudo snap install juju --classic
```

Create a Juju controller which is the management node of a Juju cloud environment. This will create
a new 

```bash
juju bootstrap microk8s microk8s-localhost
```

Create a new Juju model. Generally speaking, a model is a workspace and in the case of Kubernetes, it
is simply a new namespace.

```bash
juju add-model orchestrator
```

### Build

For now, every deployment requires all charms to be built. Soon this section will be removed and 
deployment will leverage pre-built charms published on Charmhub.

#### Bundle

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

#### Specific charm

Go to the charm directory you want to build and run:

```bash
charmcraft pack
```

### Deployment

#### Bundle

After the packages have been built you can deploy orchestrator using juju:

```bash
juju deploy ./bundle-local.yaml --trust
```

Or you can also run the `deploy.sh` bash script (which does the exact same Juju command):

```bash
./deploy.sh
```

#### Specific Charm

Specific charm deployment steps are documented in each of their README.md files.
