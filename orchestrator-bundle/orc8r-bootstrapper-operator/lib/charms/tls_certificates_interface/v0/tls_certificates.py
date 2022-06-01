# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

""" Library for the tls-certificates relation

This library contains the Requires and Provides classes for handling
the tls-certificates interface.

## Getting Started

From a charm directory, fetch the library using `charmcraft`:

```shell
charmcraft fetch-lib charms.tls_certificates_interface.v0.tls_certificates
```

You will also need to add the following library to the charm's `requirements.txt` file:
- jsonschema

### Provider charm
Example:
```python
from charms.tls_certificates_interface.v0.tls_certificates import (
    Cert,
    InsecureCertificatesProvides,
)
from ops.charm import CharmBase


class ExampleProviderCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)
        self.insecure_certificates = InsecureCertificatesProvides(self, "certificates")
        self.framework.observe(
            self.insecure_certificates.on.certificates_request, self._on_certificate_request
        )

    def _on_certificate_request(self, event):
        common_name = event.common_name
        sans = event.sans
        cert_type = event.cert_type
        certificate = self._generate_certificate(common_name, sans, cert_type)

        self.insecure_certificates.set_relation_certificate(
            certificate=certificate, relation_id=event.relation.id
        )

    def _generate_certificate(self, common_name: str, sans: list, cert_type: str) -> Cert:
        return Cert(
            common_name=common_name, cert="whatever cert", key="whatever key", ca="whatever ca"
        )
```

### Requirer charm
Example:

```python
from charms.tls_certificates_interface.v0.tls_certificates import InsecureCertificatesRequires
from ops.charm import CharmBase


class ExampleRequirerCharm(CharmBase):
    def __init__(self, *args):
        super().__init__(*args)

        self.insecure_certificates = InsecureCertificatesRequires(self, "certificates")
        self.framework.observe(
            self.insecure_certificates.on.certificate_available, self._on_certificate_available
        )
        self.insecure_certificates.request_certificate(
            cert_type="client",
            common_name="whatever common name",
        )

    def _on_certificate_available(self, event):
        certificate_data = event.certificate_data
        print(certificate_data["common_name"])
        print(certificate_data["key"])
        print(certificate_data["ca"])
        print(certificate_data["cert"])
```

"""
import json
import logging
from typing import Literal, TypedDict

from jsonschema import exceptions, validate  # type: ignore[import]
from ops.charm import CharmEvents
from ops.framework import EventBase, EventSource, Object

# The unique Charmhub library identifier, never change it
LIBID = "afd8c2bccf834997afce12c2706d2ede"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 13

REQUIRER_JSON_SCHEMA = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "examples": [
        {
            "cert_requests": [{"common_name": "whatever.com"}],
        }
    ],
    "anyOf": [
        {
            "required": ["cert_requests"],
            "type": "object",
            "properties": {
                "cert_requests": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sans": {"type": "array", "items": {"type": "string"}},
                            "common_name": {"type": "string"},
                        },
                        "required": ["common_name"],
                    },
                }
            },
        },
        {
            "type": "object",
            "required": ["client_cert_requests"],
            "properties": {
                "client_cert_requests": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sans": {"type": "array", "items": {"type": "string"}},
                            "common_name": {"type": "string"},
                        },
                        "required": ["common_name"],
                    },
                }
            },
        },
    ],
}

PROVIDER_JSON_SCHEMA = {
    "$schema": "http://json-schema.org/draft-04/schema#",
    "type": "object",
    "description": "The root schema comprises the entire JSON document. It contains the data "
    "bucket content and format for the provider of the tls-certificates relation "
    "to provide certificates to the requirer.",
    "examples": [
        {
            "certificates": [
                {
                    "common_name": "banana.com",
                    "key": "afaefawfawfawfaafe.key",
                    "cert": "abavab.crt",
                    "ca": "aefawe",
                },
                {
                    "common_name": "pizza.com",
                    "key": "aaaaaaa.key",
                    "cert": "aaa.crt",
                    "ca": "bbbbada",
                },
            ],
        }
    ],
    "properties": {
        "certificates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "common_name": {"type": "string"},
                    "key": {"type": "string"},
                    "cert": {"type": "string"},
                    "ca": {"type": "string"},
                },
                "required": ["common_name", "key", "cert", "ca"],
            },
        }
    },
    "required": ["certificates"],
}

logger = logging.getLogger(__name__)


class Cert(TypedDict):
    common_name: str
    cert: str
    key: str
    ca: str


class CertificateAvailableEvent(EventBase):
    def __init__(self, handle, certificate_data: Cert):
        super().__init__(handle)
        self.certificate_data = certificate_data

    def snapshot(self):
        return {"certificate_data": self.certificate_data}

    def restore(self, snapshot):
        self.certificate_data = snapshot["certificate_data"]


class CertificateRequestEvent(EventBase):
    def __init__(self, handle, common_name: str, sans: str, cert_type: str, relation_id: int):
        super().__init__(handle)
        self.common_name = common_name
        self.sans = sans
        self.cert_type = cert_type
        self.relation_id = relation_id

    def snapshot(self):
        return {
            "common_name": self.common_name,
            "sans": self.sans,
            "cert_type": self.cert_type,
            "relation_id": self.relation_id,
        }

    def restore(self, snapshot):
        self.common_name = snapshot["common_name"]
        self.sans = snapshot["sans"]
        self.cert_type = snapshot["cert_type"]
        self.relation_id = snapshot["relation_id"]


def _load_relation_data(raw_relation_data: dict) -> dict:
    certificate_data = dict()
    for key in raw_relation_data:
        try:
            certificate_data[key] = json.loads(raw_relation_data[key])
        except json.decoder.JSONDecodeError:
            certificate_data[key] = raw_relation_data[key]
    return certificate_data


class CertificatesProviderCharmEvents(CharmEvents):
    certificate_request = EventSource(CertificateRequestEvent)


class CertificatesRequirerCharmEvents(CharmEvents):
    certificate_available = EventSource(CertificateAvailableEvent)


class InsecureCertificatesProvides(Object):

    on = CertificatesProviderCharmEvents()

    def __init__(self, charm, relationship_name: str):
        super().__init__(charm, relationship_name)
        self.framework.observe(
            charm.on[relationship_name].relation_changed, self._on_relation_changed
        )
        self.charm = charm
        self.relationship_name = relationship_name

    @staticmethod
    def _relation_data_is_valid(certificates_data: dict) -> bool:
        """
        Uses JSON schema validator to validate relation data content.
        :param certificates_data: Certificate data dictionary as retrieved from relation data.
        :return: True/False depending on whether the relation data follows the json schema.
        """
        try:
            validate(instance=certificates_data, schema=REQUIRER_JSON_SCHEMA)
            return True
        except exceptions.ValidationError:
            return False

    def set_relation_certificate(self, certificate: Cert, relation_id: int):
        logging.info(f"Setting Certificate to {certificate} for {self.model.unit}")
        certificates_relation = self.model.get_relation(
            relation_name=self.relationship_name, relation_id=relation_id
        )
        current_certificates_json_dump = certificates_relation.data[self.model.unit].get(  # type: ignore[union-attr]  # noqa: E501
            "certificates"
        )
        current_certificate_list = []
        if current_certificates_json_dump:
            current_certificate_list = json.loads(current_certificates_json_dump)
            for cert in current_certificate_list:
                if cert["common_name"] == certificate["common_name"]:
                    logger.info("Certificate with the same common name already existed")
                    return
        current_certificate_list.append(certificate)
        certificates_relation.data[self.model.unit]["certificates"] = json.dumps(  # type: ignore[union-attr]  # noqa: E501
            current_certificate_list
        )

    def _on_relation_changed(self, event):
        logger.info(f"Raw relation data: {event.relation.data}")
        relation_data = _load_relation_data(event.relation.data[event.unit])
        logger.info(f"Parsed relation data: {relation_data}")
        if not relation_data:
            logger.info("No relation data - Deferring")
            event.defer()
            return
        if not self._relation_data_is_valid(relation_data):
            logger.info("Relation data did not pass JSON Schema validation - Deferring")
            event.defer()
            return
        for server_cert_request in relation_data.get("cert_requests", {}):
            self.on.certificate_request.emit(
                common_name=server_cert_request.get("common_name"),
                sans=server_cert_request.get("sans"),
                cert_type="server",
                relation_id=event.relation.id,
            )
        for client_cert_requests in relation_data.get("client_cert_requests", {}):
            self.on.certificate_request.emit(
                common_name=client_cert_requests.get("common_name"),
                sans=client_cert_requests.get("sans"),
                cert_type="client",
                relation_id=event.relation.id,
            )


class InsecureCertificatesRequires(Object):

    on = CertificatesRequirerCharmEvents()

    def __init__(
        self,
        charm,
        relationship_name: str,
        common_name: str = None,
        sans: list = None,
    ):
        super().__init__(charm, relationship_name)
        self.framework.observe(
            charm.on[relationship_name].relation_changed, self._on_relation_changed
        )
        self.relationship_name = relationship_name
        self.charm = charm
        self.common_name = common_name
        self.sans = sans

    def request_certificate(
        self,
        cert_type: Literal["client", "server"],
        common_name: str,
        sans: list = None,
    ):
        if not sans:
            sans = []
        logger.info("Received request to create certificate")
        relation = self.model.get_relation(self.relationship_name)
        if not relation:
            logger.info(
                f"Relation {self.relationship_name} does not exist - "
                f"The certificate request can't be completed"
            )
            return
        logger.info(f"Relation data: {relation.data}")
        relation_data = _load_relation_data(relation.data[self.model.unit])
        certificate_key_mapping = {"client": "client_cert_requests", "server": "cert_requests"}
        new_certificate_request = {"common_name": common_name, "sans": sans}
        if certificate_key_mapping[cert_type] in relation_data:
            certificate_request_list = relation_data[certificate_key_mapping[cert_type]]
            if new_certificate_request in certificate_request_list:
                logger.info("Request was already made - Doing nothing")
                return
            certificate_request_list.append(new_certificate_request)
        else:
            certificate_request_list = [new_certificate_request]
        relation.data[self.model.unit][certificate_key_mapping[cert_type]] = json.dumps(
            certificate_request_list
        )
        logger.info("Certificate request sent to provider")

    @staticmethod
    def _relation_data_is_valid(certificates_data: dict) -> bool:
        try:
            validate(instance=certificates_data, schema=PROVIDER_JSON_SCHEMA)
            return True
        except exceptions.ValidationError:
            return False

    def _on_relation_changed(self, event):
        if self.model.unit.is_leader():
            logger.info(f"Raw relation data: {event.relation.data}")
            relation_data = _load_relation_data(event.relation.data[event.unit])
            logger.info(f"Parsed relation data: {relation_data}")
            if not self._relation_data_is_valid(relation_data):
                logger.info("Relation data did not pass JSON Schema validation - Deferring")
                event.defer()
                return
            for certificate in relation_data["certificates"]:
                self.on.certificate_available.emit(certificate_data=certificate)
