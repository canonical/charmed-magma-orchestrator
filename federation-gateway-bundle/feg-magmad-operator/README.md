# magma-feg-magmad

## Description

Federation Gateway magmad service.

## Usage

Deploy using Juju:

```bash
juju deploy magma-feg-magmad feg-magmad
```

## Show gateway info
This will output a hardware ID and a challenge key. This information must be registered with the Orchestrator. 
At this time, NMS support for FeG registration is still in-progress.

```bash
juju run-action feg-magmad/0 show-gateway-info
```

After running the action you should get and ID as follows:
```bash
Action queued with id: "40"
```
NOTE: This id would be different for each run, you must copy it for the next step.

```bash
juju show-action-output <action id>
```

You should get something like:
```
UnitId: feg-magmad/0
id: "40"
results:
  result: |2+

    Hardware ID
    -----------
    6bc5ae76-48d6-40a7-bfee-8dc8a873c93a

    Challenge key
    -------------
    MHYwEAYHKoZIzj0CAQYFK4EEACIDYgAEFA7RSMifKuRYriQ5u1TBC9jlDyoeBTTosSmF8IgnEwGW0fAbP95naIMZtoYVLv9R1kYP/bIKcraVDFRbtxFzEvbG5JWWD3jjgkqr/vO5D2gy+UQVqTCRy1IrDSi9C+v/

    Build info
    -------------
     Commit Branch: unknown
     Commit Tag: unknown
     Commit Hash: unknown
     Commit Date: unknown

    Notes
    -----
    - Hardware ID is this gateway's unique identifier
    - Challenge key is this gateway's long-term keypair used for
      bootstrapping a secure connection to the cloud
    - Build info shows git commit information of this build

status: completed
timing:
  completed: 2022-08-23 13:23:19 +0000 UTC
  enqueued: 2022-08-23 13:23:16 +0000 UTC
  started: 2022-08-23 13:23:18 +0000 UTC
```

## OCI Images

Default: docker.artifactory.magmacore.org/gateway_python:latest
