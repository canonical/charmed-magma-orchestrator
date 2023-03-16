#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
import json
import logging
import subprocess
import yaml

from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)


async def deploy_postgresql(ops_test: OpsTest) -> None:
    """Deploys postrgresql-k8s charm to the integration tests Juju model.

    Args:
        ops_test: OpsTest
    """
    await ops_test.model.deploy("postgresql-k8s", application_name="postgresql-k8s")


async def deploy_orc8r_charm_from_1_6_stable_channel(
    ops_test: OpsTest, charm_name: str, application_name: str
) -> None:
    """Deploys given Magma Orc8r charm to the integration tests Juju model from 1.6/stable channel.

    Args:
        ops_test: OpsTest
        charm_name(str): Charm name
        application_name(str): Alias for the deployment
    """
    await ops_test.model.deploy(
        charm_name,
        application_name=application_name,
        channel="1.6/stable",
        trust=True,
    )


async def relate_orc8r_charm_with_postgresql(ops_test: OpsTest, application_name: str) -> None:
    """Relates give Magma Orc8r application with PostgreSQL.

    Args:
        ops_test: OpsTest
        application_name(str): Alias for the deployment
    """
    await ops_test.model.add_relation(
        relation1=application_name, relation2="postgresql-k8s:db"
    )


async def get_container_image(ops_test: OpsTest, application_name: str) -> str:
    """Returns the URL of the workload container image of a given application.

    Args:
        ops_test: OpsTest
        application_name(str): Name of the application

    Returns:
        str: Workload container image URL
    """
    cmd = [
        "sg",
        "microk8s",
        "-c",
        " ".join(
            [
                "microk8s.kubectl",
                "get",
                "pods",
                "-n",
                ops_test.model_name,
                "-o",
                "jsonpath='{.items[*].spec.containers[1].image}'",
                "-l",
                f"app.kubernetes.io/name={application_name}",
            ]
        )
    ]
    _, image, __ = await ops_test.run(*cmd)
    return image


async def get_service_details(ops_test: OpsTest, service_name: str) -> dict:
    """Returns the details of a given K8s service.

    Args:
        ops_test: OpsTest
        service_name(str): Name of the service

    Returns:
        dict: Service config
    """
    cmd = [
        "sg",
        "microk8s",
        "-c",
        " ".join(
            [
                "microk8s.kubectl",
                "-n",
                ops_test.model_name,
                "get",
                "svc",
                service_name,
                "-o",
                "json",
            ]
        )
    ]
    _, ports, __ = await ops_test.run(*cmd)
    return json.loads(ports)


async def get_juju_application_details(ops_test: OpsTest, application_name: str) -> dict:
    """Returns Juju application details as displayed by the `juju show-application` command.

    Args:
        ops_test: OpsTest
        application_name(str): Name of the application

    Returns:
        dict: Application details
    """
    cmd = ["juju", "show-application", application_name]
    _, details, __ = await ops_test.run(*cmd)
    return yaml.safe_load(details)


async def juju_refresh_application(
    ops_test: OpsTest, application_name: str, path: str, resources: dict
) -> None:
    """Refreshes/upgrades given Juju application using a charm from a local path.

    Args:
        ops_test: OpsTest
        application_name(str): Name of the application
        path(str): Path to a local charm file
        resources(dict): Resources required by the local charm file
    """
    cmd = ["juju", "refresh", application_name, "--path", path]
    for image_name, image_url in resources.items():
        cmd = cmd + ["--resource", f"{image_name}={image_url}"]
    await ops_test.run(*cmd)


def get_content_of_file_from_container(
    ops_test: OpsTest, unit: str, container_name: str, filepath: str
) -> str:
    """Returns the content of a given file from a given container of a Juju application unit.

    Args:
        ops_test: OpsTest
        unit(str): Juju application unit name
        container_name(str): Name of the container
        filepath(str): Path to a file to read from

    Returns:
        str: Content of the file
    """
    cmd = ["cat", filepath]
    file_content = run_command_in_container(ops_test, unit, container_name, cmd)
    return file_content


def get_processes_running_in_the_container(
    ops_test: OpsTest, unit: str, container_name: str
) -> dict:
    """Returns processes running inside a given container of a Juju application unit.

    Args:
        ops_test: OpsTest
        unit(str): Juju application unit name
        container_name(str): Name of the container

    Returns:
        dict: Dictionary of {PROCESS_PID}: {COMMAND}
    """
    processes = {}
    cmd = ["COLUMNS=200", "ps", "x"]
    processes_out = run_command_in_container(ops_test, unit, container_name, cmd)
    for proc in processes_out.strip().split("\r\n")[1:]:
        pid = proc.split()[0]
        cmd = " ".join(proc.split()[4:])
        processes[pid] = cmd
    return processes


def run_command_in_container(
    ops_test: OpsTest, unit: str, container_name: str, command: list
) -> str:
    """Runs given command in a given container of a Juju application unit.

    Args:
        ops_test: OpsTest
        unit(str): Juju application unit name
        container_name(str): Name of the container
        command(list): Command to execute in a form of a list

    Returns:
        str: Command's stdout
    """
    cmd = [
              "juju",
              "ssh",
              "--model",
              ops_test.model_name,
              "--container",
              container_name,
              unit,
          ] + command
    try:
        res = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        logger.error(e.stdout.decode())
        raise e
    return res.stdout.decode()
