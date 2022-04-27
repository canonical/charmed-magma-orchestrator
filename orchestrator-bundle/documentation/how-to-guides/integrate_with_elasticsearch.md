# How-to: Integrate Magma Orchestrator with elasticsearch

From the same environment where orchestrator was deployed, run:
```bash
juju config orc8r-eventd elasticsearch-url=<elasticsearch url>:<elasticsearch port>
juju config orc8r-orchestrator elasticsearch-url=<elasticsearch url>:<elasticsearch port>
```

Where `<elasticsearch url>` and `<elasticsearch port>` are your elasticsearch instance's url and port.
This address must be accessible from the environment where orchestrator is installed.
