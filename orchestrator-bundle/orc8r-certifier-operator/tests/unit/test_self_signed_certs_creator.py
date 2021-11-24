# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest
from unittest.mock import Mock

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from self_signed_certs_creator import (
    CertificateSigningRequestCreator,
    SelfSignedCertsCreator,
)


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.test_fqdns = ["some.test.fqdn"]
        self.issuer = self.subject = x509.Name(
            [x509.NameAttribute(NameOID.COMMON_NAME, self.test_fqdns[0])]
        )
        self.signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def test_given_CertificateSigningRequestCreator_when_fqdn_names_not_provided_then_value_error_is_raised(  # noqa: E501, N802
        self,
    ):
        self.assertRaises(ValueError, CertificateSigningRequestCreator, [], self.signing_key)

    def test_given_CertificateSigningRequestCreator_when_correct_params_passed_then_valid_csr_is_created(  # noqa: E501, N802
        self,
    ):
        signing_key = self.signing_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        csr = CertificateSigningRequestCreator(self.test_fqdns, signing_key)
        self.assertTrue(isinstance(csr.csr, bytes))

    def test_given_SelfSignedCertsCreator_when_fqdn_names_not_provided_then_value_error_is_raised(  # noqa: E501, N802
        self,
    ):
        self.assertRaises(ValueError, SelfSignedCertsCreator, [])

    def test_given_SelfSignedCertsCreator_when_csr_provided_without_signing_key_then_value_error_is_raised(  # noqa: E501, N802
        self,
    ):
        csr = Mock()
        signing_cert = Mock()
        self.assertRaises(
            ValueError, SelfSignedCertsCreator, self.test_fqdns, csr=csr, signing_cert=signing_cert
        )

    def test_given_SelfSignedCertsCreator_when_csr_provided_without_signing_cert_then_value_error_is_raised(  # noqa: E501, N802
        self,
    ):
        csr = Mock()
        signing_key = Mock()
        self.assertRaises(
            ValueError,
            SelfSignedCertsCreator,
            ["some.test.fqdn"],
            csr=csr,
            signing_key=signing_key,
        )

    def test_given_SelfSignedCertsCreator_when_correct_params_passed_then_valid_certificate_and_keys_are_created(  # noqa: E501, N802
        self,
    ):
        cert = SelfSignedCertsCreator(self.test_fqdns, [])
        ca = x509.load_pem_x509_certificate(cert.cert)  # type: ignore[arg-type]
        self.assertEqual(ca.subject, self.subject)
        self.assertEqual(ca.issuer, self.issuer)
        self.assertTrue(isinstance(cert.cert, bytes))
        self.assertTrue(isinstance(cert.private_key, bytes))

    def test_given_SelfSignedCertsCreator_when_csr_with_signing_cert_and_signing_key_passed_then_valid_certificate_is_created(  # noqa: E501, N802
        self,
    ):
        csr_signing_key = self.signing_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        initial_csr = CertificateSigningRequestCreator(self.test_fqdns, csr_signing_key)
        signing_cert = SelfSignedCertsCreator(self.test_fqdns, [])
        cert = SelfSignedCertsCreator(
            self.test_fqdns,
            csr=initial_csr.csr,
            signing_cert=signing_cert.cert,
            signing_key=signing_cert.private_key,
        )
        ca_cert = x509.load_pem_x509_certificate(signing_cert.cert)  # type: ignore[arg-type]
        csr = x509.load_pem_x509_csr(initial_csr.csr)  # type: ignore[arg-type]
        output_cert = x509.load_pem_x509_certificate(cert.cert)  # type: ignore[arg-type]

        self.assertTrue(isinstance(cert.cert, bytes))
        self.assertEqual(output_cert.subject, csr.subject)
        self.assertEqual(
            output_cert.public_key().public_bytes(
                encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.PKCS1
            ),
            csr.public_key().public_bytes(
                encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.PKCS1
            ),
        )
        self.assertEqual(output_cert.issuer, ca_cert.issuer)
