#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import boto3


class STS:
    def __init__(self):
        self.client = boto3.client("sts")

    def get_caller_identity(self):
        return self.client.get_caller_identity()
