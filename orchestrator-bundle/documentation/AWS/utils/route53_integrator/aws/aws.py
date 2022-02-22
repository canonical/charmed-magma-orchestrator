#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import botocore

from aws.elb import ELB
from aws.route53 import Route53
from aws.sts import STS


class AWSError(Exception):
    pass


class CredentialsError(AWSError):
    def __init__(self):
        self.message = "Bad credentials were provided. Validate that you can use the AWS CLI to " \
                       "do actions such as communicate with route53 and ELB."
        super().__init__(self.message)


class AWS:
    def __init__(self):
        self.route53 = Route53()
        self.elb = ELB()
        self.sts = STS()
        self._validate_credentials()

    def _validate_credentials(self):
        """
        Validates AWS credentials by making a call to AWS
        """
        try:
            self.sts.get_caller_identity()
        except botocore.exceptions.ClientError:
            raise CredentialsError()
