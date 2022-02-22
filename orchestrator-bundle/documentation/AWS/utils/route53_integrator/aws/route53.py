#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import random
from datetime import date

import boto3


class Route53:
    def __init__(self):
        self.client = boto3.client("route53")

    @property
    def _caller_reference(self) -> str:
        """
        Builds unique caller reference
        :return: Caller reference
        """
        todays_date = date.today()
        random_number = random.randint(1000, 9999)
        return f"juju-{todays_date.year}-{todays_date.month}-{todays_date.day}-{random_number}"

    def list_hosted_zones(self) -> list:
        """
        Gets all hosted zones
        :return: Dict of all hosted zones
        """
        hosted_zones = self.client.list_hosted_zones()
        return hosted_zones["HostedZones"]

    def create_hosted_zone(self, name: str) -> dict:
        """
        Creates Hosted Zone

        :param name: Zone name
        :return: Zone
        """
        logging.info("Creating hosted zone")
        hosted_zone = self.client.create_hosted_zone(
            Name=name, CallerReference=self._caller_reference
        )
        logging.info("Hosted zone created")
        return hosted_zone

    def get_hosted_zone(self, zone_id: str) -> dict:
        """
        Retrieves zone based on ID

        :param zone_id: Zone ID
        :return: Zone
        """
        logging.info(f"Getting hosted zone {zone_id}")
        hosted_zone = self.client.get_hosted_zone(Id=zone_id)
        return hosted_zone

    def get_zone_by_name(self, name: str) -> dict:
        """
        Retrieves zone based on name

        :param name: Zone name
        :return: Zone (or empty dict)
        """
        hosted_zones = self.list_hosted_zones()
        for zone in hosted_zones:
            zone_name = zone["Name"][:-1]
            if zone_name == name:
                return zone
        return {}

    def create_hosted_zone_if_doesnt_exist(self, name: str) -> dict:
        """
        Checks if zone exists based on name and creates one if it isn't the case.
        :param name: Hosted zone name
        :return: Hosted Zone
        """
        zone = self.get_zone_by_name(name)
        if zone:
            logging.info("Zone already exists, not creating a new one.")
            return self.get_hosted_zone(zone["Id"].split("/")[-1])
        else:
            return self.create_hosted_zone(name)

    def create_alias_resource_a_record(
            self,
            name: str,
            alias_target_hosted_zone_id: str,
            alias_target_dns_name: str,
            hosted_zone_id: str,
    ):
        """
        Creates an A record associated with an Alias.

        :param name: A record name
        :param alias_target_hosted_zone_id: Alias target hosted zone id
        :param alias_target_dns_name: Alias target DNS name
        :param hosted_zone_id: Route53 Hosted Zone ID
        """
        logging.info(f"Creating alias resource A record for {name}")
        change_batch = {
            "Comment": "Creating Alias resource record sets in Route 53",
            "Changes": [{
                "Action": "CREATE",
                "ResourceRecordSet": {
                    "Name": name,
                    "Type": "A",
                    "AliasTarget": {
                        "HostedZoneId": alias_target_hosted_zone_id,
                        "DNSName": alias_target_dns_name,
                        "EvaluateTargetHealth": True
                    }}
            },
            ]
        }
        try:
            self.client.change_resource_record_sets(
                HostedZoneId=hosted_zone_id,
                ChangeBatch=change_batch
            )
            logging.info(f"Alias resource created for {name}")
        except self.client.exceptions.InvalidChangeBatch as e:
            if "already exists" in str(e):
                logging.info(f"A Record {name} already exists in hosted zone, not doing anything")
            else:
                raise e
