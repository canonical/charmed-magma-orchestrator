#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12


def generate_certificate(
    csr: bytes,
    ca: bytes,
    ca_key: bytes,
    validity: int = 365,
    alt_names: list = None,
) -> bytes:
    """
    :param csr: CSR Bytes
    :param ca: Set the CA certificate, must be PEM format
    :param ca_key: The CA key, must be PEM format; if not in CAfile
    :param validity: Validity
    :param alt_names: Alternative names (optional)
    :return:
    """
    csr_object = x509.load_pem_x509_csr(csr)
    subject = csr_object.subject
    issuer = x509.load_pem_x509_certificate(ca).issuer
    private_key = serialization.load_pem_private_key(ca_key, password=None)

    certificate_builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(csr_object.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=validity))
    )

    if alt_names:
        names = [x509.DNSName(n) for n in alt_names]
        certificate_builder = certificate_builder.add_extension(
            x509.SubjectAlternativeName(names),
            critical=False,
        )
    certificate_builder._version = x509.Version.v1
    cert = certificate_builder.sign(private_key, hashes.SHA256())
    return cert.public_bytes(serialization.Encoding.PEM)


def generate_csr(private_key: bytes, subject: str, country: str = "US") -> bytes:
    """

    :param private_key: Private key to use
    :param subject: Output the request's subject
    :param country: Country
    :return:
    """

    subject = x509.Name(
        [
            x509.NameAttribute(x509.NameOID.COUNTRY_NAME, country),
            x509.NameAttribute(x509.NameOID.COMMON_NAME, subject),
        ]
    )
    signing_key = serialization.load_pem_private_key(private_key, password=None)
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(subject)
        .sign(signing_key, hashes.SHA256())
    )
    csr_bytes = csr.public_bytes(serialization.Encoding.PEM)
    return csr_bytes


def generate_ca(
    private_key: bytes,
    subject: str,
    validity: int = 365,
    country: str = "US",
) -> bytes:
    """

    :param private_key: Private key to use
    :param subject: Output the request's subject
    :param validity time (in days)
    :param country name
    :return:
    """
    private_key_object = serialization.load_pem_private_key(private_key, password=None)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(x509.NameOID.COUNTRY_NAME, country),
            x509.NameAttribute(x509.NameOID.COMMON_NAME, subject),
        ]
    )
    subject_identifier_object = x509.SubjectKeyIdentifier.from_public_key(
        private_key_object.public_key()
    )
    subject_identifier = key_identifier = subject_identifier_object.public_bytes()
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key_object.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=validity))
        .add_extension(x509.SubjectKeyIdentifier(digest=subject_identifier), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier(
                key_identifier=key_identifier,
                authority_cert_issuer=None,
                authority_cert_serial_number=None,
            ),
            critical=False,
        )
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
        .sign(private_key_object, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM)


def generate_private_key(key_size: int = 2048, public_exponent: int = 65537) -> bytes:
    private_key = rsa.generate_private_key(
        public_exponent=public_exponent,
        key_size=key_size,
    )
    key_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return key_bytes


def generate_pfx_package(
    certificate: bytes,
    private_key: bytes,
    password: str,
) -> bytes:
    private_key_object = serialization.load_pem_private_key(private_key, password=None)
    certificate_object = x509.load_pem_x509_certificate(certificate)
    name = certificate_object.subject.rfc4514_string()
    pfx_bytes = pkcs12.serialize_key_and_certificates(
        name=name.encode(),
        cert=certificate_object,
        key=private_key_object,  # type: ignore[arg-type]
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(password.encode()),
    )
    return pfx_bytes
