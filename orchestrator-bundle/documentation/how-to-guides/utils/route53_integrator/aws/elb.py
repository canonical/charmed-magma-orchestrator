#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging

import boto3


class ELB:
    def __init__(self):
        self.client = boto3.client("elb")
        self.load_balancers = None

    def _get_load_balancers(self):
        """
        Retrieves all load balancers from ELB and sets the load_balancers attribute
        """
        logging.info("Retrieving all load balancers")
        self.load_balancers = self.client.describe_load_balancers()

    def get_hosted_zone_id(self, elb: str) -> str:
        """
        Retrieves hosted zone id based on ELB address
        :param elb: ELB address (ex. 123-789.us-east-1.elb.amazonaws.com)
        :return: Hosted Zone ID
        """
        if not self.load_balancers:
            self._get_load_balancers()
        logging.info(f"Retrieving ELB hosted zone id for {elb}")
        for load_balancer in self.load_balancers["LoadBalancerDescriptions"]:
            if load_balancer["DNSName"] == elb:
                logging.info(f"ELB hosted zone id: {load_balancer['CanonicalHostedZoneNameID']}")
                return load_balancer["CanonicalHostedZoneNameID"]
        raise ValueError(f"Could not find load balancer for elb: {elb}")
