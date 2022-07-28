#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Contains methods used to generate TLS certificates."""
import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12


def generate_ca(
    private_key: bytes,
    subject: str,
    validity: int = 365,
    country: str = "US",
) -> bytes:
    """Generates a CA Certificate.

    Args:
        private_key (bytes): Private key.
        subject (str): Certificate subject.
        validity (int): Certificate validity time (in days)
        country (str): Certificate Issuing country.

    Returns:
        bytes: CA Certificate.
    """
    private_key_object = serialization.load_pem_private_key(private_key, password=None)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(x509.NameOID.COUNTRY_NAME, country),
            x509.NameAttribute(x509.NameOID.COMMON_NAME, subject),
        ]
    )
    subject_identifier_object = x509.SubjectKeyIdentifier.from_public_key(
        private_key_object.public_key()  # type: ignore[arg-type]
    )
    subject_identifier = key_identifier = subject_identifier_object.public_bytes()
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key_object.public_key())  # type: ignore[arg-type]
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
        .sign(private_key_object, hashes.SHA256())  # type: ignore[arg-type]
    )
    return cert.public_bytes(serialization.Encoding.PEM)


def generate_certificate(
    csr: bytes,
    ca: bytes,
    ca_key: bytes,
    validity: int = 365,
    alt_names: list = None,
) -> bytes:
    """Generates a TLS certificate based on a CSR.

    Args:
        csr (bytes): CSR
        ca (bytes): CA Certificate.
        ca_key (bytes): CA private key.
        validity (int): Certificate validity (in days)
        alt_names: Certificate Subject alternative names

    Returns:
        bytes: Certificate
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
    cert = certificate_builder.sign(private_key, hashes.SHA256())  # type: ignore[arg-type]
    return cert.public_bytes(serialization.Encoding.PEM)


def generate_csr(private_key: bytes, subject: str) -> bytes:
    """Generates a CSR using private key and subject.

    Args:
        private_key: Private Key.
        subject: CSR Subject.

    Returns:
        bytes: CSR
    """
    subject = x509.Name(
        [
            x509.NameAttribute(x509.NameOID.COMMON_NAME, subject),
        ]
    )
    signing_key = serialization.load_pem_private_key(private_key, password=None)
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(subject)
        .sign(signing_key, hashes.SHA256())  # type: ignore[arg-type]
    )
    csr_bytes = csr.public_bytes(serialization.Encoding.PEM)
    return csr_bytes


def generate_private_key(key_size: int = 2048, public_exponent: int = 65537) -> bytes:
    """Generates a private key.

    Args:
        key_size (int): Key size in bytes
        public_exponent: Public exponent.

    Returns:
        bytes: Private Key
    """
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
    """Generates a PFX package to contain the TLS certificate and private key.

    Args:
        certificate (bytes): TLS certificate.
        private_key (bytes): Private key.
        password (str): Password to open the PFX package.

    Returns:
        bytes:
    """
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
