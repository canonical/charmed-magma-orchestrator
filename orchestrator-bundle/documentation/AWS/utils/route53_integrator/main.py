#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import argparse
import logging

from aws.aws import AWS
from k8s.k8s import K8s

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s'
)


DESCRIPTION = """
Script that communicates with AWS and creates the following objects in Route53. Those objects
are a hosted zone and four A records based on Kubernetes LoadBalancer services. For this script
to work correctly, aws cli and kubectl must already be configured.
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


def main():
    hosted_zone, namespace = parse_arguments()
    aws = AWS()
    k8s = K8s(namespace)

    route53_zone = aws.route53.create_hosted_zone_if_doesnt_exist(hosted_zone)
    route53_zone_id = route53_zone["HostedZone"]["Id"].split("/")[-1]

    service_mapping = {
        "nginx-proxy": f"*.nms.{hosted_zone}",
        "orc8r-bootstrap-nginx": f"bootstrapper-controller.{hosted_zone}",
        "orc8r-clientcert-nginx": f"controller.{hosted_zone}",
        "orc8r-nginx-proxy": f"api.{hosted_zone}",
    }
    for service in service_mapping:
        load_balancer_address = k8s.get_service_load_balancer_address(service)
        elb_hosted_zone = aws.elb.get_hosted_zone_id(load_balancer_address)
        aws.route53.create_alias_resource_a_record(
            name=service_mapping[service],
            alias_target_dns_name=load_balancer_address,
            alias_target_hosted_zone_id=elb_hosted_zone,
            hosted_zone_id=route53_zone_id
        )
    nameservers = route53_zone["DelegationSet"]["NameServers"]
    logging.info("Done!")
    logging.info(f"Nameservers: {nameservers}")


if __name__ == "__main__":
    main()
