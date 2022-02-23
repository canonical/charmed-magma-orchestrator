#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import argparse
import logging
from dataclasses import dataclass

from tabulate import tabulate

from aws.aws import AWS
from k8s.k8s import K8s

logging.basicConfig(
    level=logging.ERROR,
    format='[%(asctime)s] %(levelname)s - %(message)s'
)


DESCRIPTION = """
Script that communicates with AWS Route53 and creates a hosted zone and four A records based on 
four Kubernetes LoadBalancer services. For this script to work correctly, aws cli and kubectl must 
already be configured.
"""


def parse_arguments() -> (str, str):
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument(
        '--hosted_zone',
        type=str,
        help='Domain name for your hosted zone',
        required=True
    )
    parser.add_argument(
        '--namespace',
        type=str,
        help='Kubernetes namespace',
        required=True
    )
    args = parser.parse_args()
    return args.hosted_zone, args.namespace


@dataclass
class ARecord:
    kubernetes_service: str
    a_record_name: str
    load_balancer_address: str = ""
    elb_hosted_zone: str = ""


def print_disclaimer(hosted_zone: str, a_records: [ARecord]):
    headers = ["A Record Name", "LoadBalancer Address", "Kubernetes Service"]
    data_list = [
        [
            a_records[i].a_record_name,
            a_records[i].load_balancer_address,
            a_records[i].kubernetes_service,
        ]
        for i in range(len(a_records))
    ]
    print(f"\nThe hosted zone {hosted_zone} will be created with the following A records:")
    print("\n")
    print(tabulate(data_list, headers=headers))
    input("\nPress Enter to continue...")


def print_nameservers(nameservers: [str]):
    nameserver_list = []
    for nameserver in nameservers:
        nameserver_list.append([nameserver])
    print("\nDone! Configure your domain registrar to use those nameservers:")
    print(tabulate(nameserver_list))


def main():
    hosted_zone, namespace = parse_arguments()
    aws = AWS()
    k8s = K8s(namespace)
    a_records = [
        ARecord(
            kubernetes_service="nginx-proxy",
            a_record_name=f"*.nms.{hosted_zone}",
        ),
        ARecord(
            kubernetes_service="orc8r-bootstrap-nginx",
            a_record_name=f"bootstrapper-controller.{hosted_zone}",
        ),
        ARecord(
            kubernetes_service="orc8r-clientcert-nginx",
            a_record_name=f"controller.{hosted_zone}",
        ),
        ARecord(
            kubernetes_service="orc8r-nginx-proxy",
            a_record_name=f"api.{hosted_zone}",
        ),
    ]

    for a_record in a_records:
        load_balancer_address = k8s.get_service_load_balancer_address(a_record.kubernetes_service)
        elb_hosted_zone = aws.elb.get_hosted_zone_id(load_balancer_address)
        a_record.load_balancer_address = load_balancer_address
        a_record.elb_hosted_zone = elb_hosted_zone

    print_disclaimer(hosted_zone, a_records)

    route53_zone = aws.route53.create_hosted_zone_if_doesnt_exist(hosted_zone)
    route53_zone_id = route53_zone["HostedZone"]["Id"].split("/")[-1]

    for a_record in a_records:
        aws.route53.create_alias_resource_a_record(
            name=a_record.a_record_name,
            alias_target_dns_name=a_record.load_balancer_address,
            alias_target_hosted_zone_id=a_record.elb_hosted_zone,
            hosted_zone_id=route53_zone_id
        )
    nameservers = route53_zone["DelegationSet"]["NameServers"]
    print_nameservers(nameservers)


if __name__ == "__main__":
    main()
