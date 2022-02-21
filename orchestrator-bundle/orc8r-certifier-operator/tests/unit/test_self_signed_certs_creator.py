#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.


from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs12

from self_signed_certs_creator import (
    generate_ca,
    generate_certificate,
    generate_csr,
    generate_pfx_package,
    generate_private_key,
)


def validate_induced_data_from_pfx_is_equal_to_initial_data(
    pfx_file: bytes,
    password: str,
    initial_certificate: bytes,
    initial_private_key: bytes,
):
    (
        induced_private_key_object,
        induced_certificate_object,
        additional_certificate,
    ) = pkcs12.load_key_and_certificates(pfx_file, password.encode())

    initial_private_key_object = serialization.load_pem_private_key(
        initial_private_key,
        password=None,
    )
    initial_public_key_object = initial_private_key_object.public_key()
    induced_public_key_object = induced_private_key_object.public_key()  # type: ignore[union-attr]
    induced_certificate = induced_certificate_object.public_bytes(  # type: ignore[union-attr]
        encoding=serialization.Encoding.PEM
    )

    initial_public_key = initial_public_key_object.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.PKCS1,
    )
    induced_public_key = induced_public_key_object.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.PKCS1,
    )
    induced_private_key = induced_private_key_object.private_bytes(  # type: ignore[union-attr]
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    assert initial_public_key == induced_public_key
    assert induced_certificate == initial_certificate
    assert initial_private_key == induced_private_key


def test_given_key_size_provided_when_generate_private_key_then_private_key_is_generated():
    key_size = 1234

    private_key = generate_private_key(key_size=key_size)

    private_key_object = serialization.load_pem_private_key(private_key, password=None)
    assert isinstance(private_key_object, rsa.RSAPrivateKeyWithSerialization)
    assert private_key_object.key_size == key_size


def test_given_private_key_and_subject_when_generate_ca_then_ca_is_generated_correctly():
    subject = "certifier.example.com"
    private_key = generate_private_key()

    certifier_pem = generate_ca(private_key=private_key, subject=subject)

    cert = x509.load_pem_x509_certificate(certifier_pem)
    private_key_object = serialization.load_pem_private_key(private_key, password=None)
    certificate_public_key = cert.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.PKCS1,
    )
    initial_public_key = private_key_object.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.PKCS1,
    )

    assert cert.issuer == x509.Name(
        [
            x509.NameAttribute(x509.NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(x509.NameOID.COMMON_NAME, subject),
        ]
    )
    assert cert.subject == x509.Name(
        [
            x509.NameAttribute(x509.NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(x509.NameOID.COMMON_NAME, subject),
        ]
    )
    assert certificate_public_key == initial_public_key


def test_given_private_key_and_subject_when_generate_csr_then_csr_is_created():
    private_key = generate_private_key()
    subject = "whatever.com"

    csr = generate_csr(private_key=private_key, subject=subject)

    csr_object = x509.load_pem_x509_csr(csr)
    assert csr_object.is_signature_valid is True
    assert csr_object.subject == x509.Name(
        [
            x509.NameAttribute(x509.NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(x509.NameOID.COMMON_NAME, subject),
        ]
    )


def test_given_csr_and_ca_when_generate_certificate_then_certificate_is_generated_with_correct_subject_and_issuer():  # noqa: E501
    ca_subject = "whatever.ca.subject"
    csr_subject = "whatever.csr.subject"
    ca_key = generate_private_key()
    ca = generate_ca(
        private_key=ca_key,
        subject=ca_subject,
    )
    csr_private_key = generate_private_key()
    csr = generate_csr(
        private_key=csr_private_key,
        subject=csr_subject,
    )
    certificate = generate_certificate(
        csr=csr,
        ca=ca,
        ca_key=ca_key,
    )
    certificate_object = x509.load_pem_x509_certificate(certificate)
    assert certificate_object.issuer == x509.Name(
        [
            x509.NameAttribute(x509.NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(x509.NameOID.COMMON_NAME, ca_subject),
        ]
    )
    assert certificate_object.subject == x509.Name(
        [
            x509.NameAttribute(x509.NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(x509.NameOID.COMMON_NAME, csr_subject),
        ]
    )


def test_given_alt_names_when_generate_certificate_then_alt_names_are_correctly_populated():
    ca_subject = "whatever.ca.subject"
    csr_subject = "whatever.csr.subject"
    alt_name_1 = "*.example.com"
    alt_name_2 = "*.nms.example.com"
    ca_key = generate_private_key()
    ca = generate_ca(
        private_key=ca_key,
        subject=ca_subject,
    )
    csr_private_key = generate_private_key()
    csr = generate_csr(
        private_key=csr_private_key,
        subject=csr_subject,
    )
    certificate = generate_certificate(
        csr=csr, ca=ca, ca_key=ca_key, alt_names=[alt_name_1, alt_name_2]
    )
    certificate_object = x509.load_pem_x509_certificate(certificate)
    alt_names = certificate_object.extensions.get_extension_for_class(
        x509.extensions.SubjectAlternativeName
    )
    alt_name_strings = [alt_name.value for alt_name in alt_names.value]
    assert len(alt_name_strings) == 2
    assert alt_name_1 in alt_name_strings
    assert alt_name_2 in alt_name_strings


def test_given_basic_constraint_is_false_when_generate_ca_then_extensions_are_correctly_populated():  # noqa: E501
    subject = "whatever.ca.subject"

    private_key = generate_private_key()
    ca = generate_ca(
        private_key=private_key,
        subject=subject,
    )
    certificate_object = x509.load_pem_x509_certificate(ca)
    basic_constraints = certificate_object.extensions.get_extension_for_class(
        x509.extensions.BasicConstraints
    )
    assert basic_constraints.value.ca is True


def test_given_certificate_created_when_verify_public_key_then_no_exception_is_thrown():
    ca_subject = "whatever.ca.subject"
    csr_subject = "whatever.csr.subject"
    ca_key = generate_private_key()
    ca = generate_ca(
        private_key=ca_key,
        subject=ca_subject,
    )
    csr_private_key = generate_private_key()
    csr = generate_csr(
        private_key=csr_private_key,
        subject=csr_subject,
    )
    certificate = generate_certificate(
        csr=csr,
        ca=ca,
        ca_key=ca_key,
    )

    certificate_object = x509.load_pem_x509_certificate(certificate)
    private_key_object = serialization.load_pem_private_key(ca_key, password=None)
    public_key = private_key_object.public_key()

    public_key.verify(  # type: ignore[call-arg]
        certificate_object.signature,
        certificate_object.tbs_certificate_bytes,
        padding.PKCS1v15(),  # type: ignore[arg-type]
        certificate_object.signature_hash_algorithm,  # type: ignore[arg-type]
    )


def test_given_cert_and_private_key_when_generate_pfx_package_then_pfx_file_is_generated():
    password = "whatever"
    ca_subject = "whatever.ca.subject"
    csr_subject = "whatever.csr.subject"
    certifier_key = generate_private_key()
    certifier_pem = generate_ca(
        private_key=certifier_key,
        subject=ca_subject,
    )
    admin_operator_key_pem = generate_private_key()
    admin_operator_csr = generate_csr(
        private_key=admin_operator_key_pem,
        subject=csr_subject,
    )
    admin_operator_pem = generate_certificate(
        csr=admin_operator_csr,
        ca=certifier_pem,
        ca_key=certifier_key,
    )
    admin_operator_pfx = generate_pfx_package(
        private_key=admin_operator_key_pem,
        certificate=admin_operator_pem,
        password=password,
    )

    validate_induced_data_from_pfx_is_equal_to_initial_data(
        pfx_file=admin_operator_pfx,
        password=password,
        initial_certificate=admin_operator_pem,
        initial_private_key=admin_operator_key_pem,
    )
