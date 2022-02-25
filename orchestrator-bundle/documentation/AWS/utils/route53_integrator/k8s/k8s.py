#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import httpx
from lightkube import Client
from lightkube.core.exceptions import ConfigError
from lightkube.resources.core_v1 import Service, Node


class K8sError(Exception):
    pass


class CredentialsError(K8sError):
    def __init__(self):
        self.message = "Bad credentials were provided. Validate that you can use the kubectl to " \
                       "do actions such as getting services"
        super().__init__(self.message)


class K8s:
    def __init__(self, namespace: str):
        self.namespace = namespace
        self.client = Client(timeout=httpx.Timeout(10))
        self._validate_credentials()

    def _validate_credentials(self):
        """
        Tries credentials against an API call to kubernetes and raises if it fails
        """
        try:
            for _ in self.client.list(Node):
                pass
        except (ConfigError, httpx.ConnectTimeout):
            raise CredentialsError()

    def get_service(self, name: str) -> Service:
        """
        Gets service from Kubernetes based on name

        :param name: Service name
        :return: Service object
        """
        logging.info(f"Getting service {name} from kubernetes")
        return self.client.get(Service, name, namespace=self.namespace)

    def get_service_load_balancer_address(self, name: str) -> str:
        """
        Retrieves LoadBalancer address based on service name
        :param name: Service name
        :return: LoadBalancer address
        """
        logging.info(f"Getting LoadBalancer address for service {name}")
        service = self.get_service(name)
        ingresses = service.status.loadBalancer.ingress
        load_balancer_hostname = ingresses[0].hostname
        logging.info(f"LoadBalancer address: {load_balancer_hostname}")
        return load_balancer_hostname
