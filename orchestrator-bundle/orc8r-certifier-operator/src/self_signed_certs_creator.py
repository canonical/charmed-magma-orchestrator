# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import datetime
from ipaddress import IPv4Address
from typing import List

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


class SelfSignedCertsCreator:
    """A class used for generating self-signed RSA TLS certificates"""

    def __init__(
        self,
        names: List[str],
        ips: List[IPv4Address] = [],
        csr=None,
        signing_cert=None,
        signing_key=None,
        key_size: int = 2048,
        validity: int = 365,
    ):
        """Initialise a new self-signed certificate.

        Args:
            names: A list of FQDNs that should be placed in the Subject Alternative
                Name field of the certificate. The first name in the list will be
                used as the Common Name, Subject and Issuer field.
            ips: A list of IPv4Address objects that  should be present in the list
                of Subject Alternative Names of the certificate.
            csr: A CSR (Certificate Signing Request) to sign. If passed, Subject and PublicKey
                fields of the created certificate will be taken from the CSR.
            signing_cert: Needed only when CSR used. This CA cert is used to populate Issuer
                field on the created certificate.
            signing_key: A private key used to sign the certificate. If none given, new key will
                be generate.
            key_size: Size of the RSA Private Key to be generated. Defaults to 2048
            validity: Period in days the certificate is valid for. Default is 365.

        Raises:
            ValueError: is raised if an empty list of names is provided to the
                constructor or when trying to sign a CSR without passing signing cert and
                signing key parameters.
        """

        # Ensure that at least one FQDN was provided
        # TODO: Do some validation on any provided names
        if not names:
            raise ValueError("Must provide at least one name for the certificate")
        # Ensure that at least one FQDN was provided
        if csr and (not signing_key or not signing_cert):
            raise ValueError(
                "When signing CSR both signing cert and signing key need to be provided!"
            )

        # Create a list of x509.DNSName objects from the list of FQDNs provided
        self.names = [x509.DNSName(n) for n in names]
        # Create a list of x509IPAddress objects from the list of IPv4Addresses
        self.ips = [x509.IPAddress(i) for i in ips] if ips else []
        # Sign CSR
        self.csr = csr
        # Use existing CA
        self.signing_cert = signing_cert
        self.signing_key = signing_key
        # Initialise some values
        self.key_size = key_size
        self.validity = validity
        self.cert = None
        self.public_key = None
        self.private_key = None
        self._generate_cert()

    def _generate_cert(self):
        """Generate a self-signed certificate"""
        if self.csr:
            subject = x509.load_pem_x509_csr(self.csr).subject
            issuer = x509.load_pem_x509_certificate(self.signing_cert).issuer
            public_key = x509.load_pem_x509_csr(self.csr)
            signing_key = serialization.load_pem_private_key(self.signing_key, password=None)
        else:
            # Set the subject/issuer to the first of the given names
            subject = issuer = x509.Name(
                [x509.NameAttribute(NameOID.COMMON_NAME, self.names[0].value)]
            )
            signing_key = (
                self.signing_key
                if self.signing_key
                else rsa.generate_private_key(public_exponent=65537, key_size=self.key_size)
            )
            public_key = signing_key  # type: ignore[assignment]

        # Build the cert
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(public_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=self.validity))
            .add_extension(x509.SubjectAlternativeName(self.names and self.ips), critical=False)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_encipherment=True,
                    key_cert_sign=False,
                    key_agreement=False,
                    content_commitment=False,
                    data_encipherment=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage(
                    [
                        x509.oid.ExtendedKeyUsageOID.SERVER_AUTH,
                        x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH,
                    ]
                ),
                critical=False,
            )
            .sign(signing_key, hashes.SHA256())
        )
        self.cert = cert.public_bytes(serialization.Encoding.PEM)  # type: ignore[assignment]
        self.private_key = signing_key.private_bytes(  # type: ignore[assignment]
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )


class CertificateSigningRequestCreator:
    """A class used for generating CSRs (Certificate Signing Requests)"""

    def __init__(
        self,
        names: List[str],
        signing_key,
    ):
        """Create a new Certificate Signing Request (CSR).

        Args:
            names: A list of FQDNs that should be placed in the Subject Alternative
                Name field of the certificate. The first name in the list will be
                used as the Common Name, Subject and Issuer field.
            signing_key: A private key used to sign the certificate. If none given, new key will
                be generate.

        Raises:
            ValueError: is raised if an empty list of names is provided to the
                constructor.
        """

        # Ensure that at least one FQDN was provided
        # TODO: Do some validation on any provided names
        if not names:
            raise ValueError("Must provide at least one name for the CSR!")

        # Create a list of x509.DNSName objects from the list of FQDNs provided
        self.names = [x509.DNSName(n) for n in names]
        self.signing_key = signing_key
        self.csr = None
        self._generate_csr()

    def _generate_csr(self):
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, self.names[0].value)])
        signing_key = serialization.load_pem_private_key(self.signing_key, password=None)

        # Generate CSR
        csr = (
            x509.CertificateSigningRequestBuilder()
            .subject_name(subject)
            .sign(signing_key, hashes.SHA256())
        )
        self.csr = csr.public_bytes(serialization.Encoding.PEM)  # type: ignore[assignment]
