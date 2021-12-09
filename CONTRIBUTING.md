# Contributing / Hacking

## Intended use case

The charms and bundles in this repository are specifically developed for the 
[magma](https://www.magmacore.org/) usecase.

## Roadmap

1. Charm Magma Orchestrator (microk8s)
2. Charm Magma Access Gateway with MAAS (Bare metal)
3. Charm Magma Federation Gateway (microk8s)
4. Validate public cloud deployments (AWS, GCP and Azure)

## Code contributions
If you want to propose a new feature, a bug fix or a documentation improvement:
- Create a new branch from main.
- Commit and push your changes to this branch.
- Validate that all Github actions pass.
- Create a pull request in [github](https://github.com/canonical/charmed-magma/pulls).
- Your pull request will be reviewed by one of the repository maintainer.

Note that each component has its own `CONTRIBURING.md` file that will detail how you can test, 
deploy and publish this specific component. Please refer to that file.

## Continuous Integration
On each code push and pull request made in Github, a series of validations are triggered through 
Github actions:
- Linting validation
- Static analysis
- Unit tests
- Integration tests

All of them must pass for a change to be reviewed.
