"""DNS-01 certificate issuance; private material stays outside the repository."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID


def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def private_write(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
    path.chmod(0o600)


class Acme:
    def __init__(self, directory: str, key: rsa.RSAPrivateKey):
        self.http = httpx.Client(timeout=30)
        self.directory = self.http.get(directory).raise_for_status().json()
        self.key = key
        numbers = key.public_key().public_numbers()
        self.jwk = {
            "e": b64(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")),
            "kty": "RSA",
            "n": b64(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
        }
        self.kid: str | None = None
        self.nonce: str | None = None

    def post(self, url: str, payload: dict | None) -> httpx.Response:
        for attempt in range(2):
            if self.nonce is None:
                self.nonce = self.http.head(self.directory["newNonce"]).raise_for_status().headers["Replay-Nonce"]
            protected = {"alg": "RS256", "nonce": self.nonce, "url": url}
            protected.update({"kid": self.kid} if self.kid else {"jwk": self.jwk})
            encoded_header = b64(json.dumps(protected, separators=(",", ":")).encode())
            encoded_payload = "" if payload is None else b64(json.dumps(payload, separators=(",", ":")).encode())
            signing_input = f"{encoded_header}.{encoded_payload}".encode()
            signature = self.key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
            response = self.http.post(
                url,
                headers={"Content-Type": "application/jose+json"},
                json={"protected": encoded_header, "payload": encoded_payload, "signature": b64(signature)},
            )
            self.nonce = response.headers.get("Replay-Nonce")
            if response.status_code == 400 and response.json().get("type", "").endswith(":badNonce") and attempt == 0:
                continue
            response.raise_for_status()
            return response
        raise RuntimeError("ACME nonce retry exhausted.")

    def poll(self, url: str, states: set[str], timeout: int = 180) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            item = self.post(url, None).json()
            if item["status"] in states:
                return item
            if item["status"] in {"invalid", "expired", "revoked", "deactivated"}:
                problems = [entry.get("error") for entry in item.get("challenges", []) if entry.get("error")]
                raise RuntimeError(f"ACME authorization/order status: {item['status']}; problems: {json.dumps(problems)}.")
            time.sleep(3)
        raise TimeoutError("ACME operation timed out; reconcile authorization before retrying.")


def ensure_certificate(
    directory: str,
    host: str,
    root: Path,
    add_txt: Callable[[str], None],
    txt_visible: Callable[[str], bool],
    remove_txt: Callable[[str], None],
) -> Path:
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    cert_path = root / "certificate.pem"
    pfx_path = root / "certificate.pfx"
    if cert_path.exists() and pfx_path.exists():
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        if host in names.get_values_for_type(x509.DNSName) and cert.not_valid_after_utc > datetime.now(timezone.utc) + timedelta(days=21):
            return pfx_path
    account_path = root / "account.pem"
    if account_path.exists():
        account_key = serialization.load_pem_private_key(account_path.read_bytes(), password=None)
        if not isinstance(account_key, rsa.RSAPrivateKey):
            raise ValueError("ACME account key must be RSA.")
    else:
        account_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_write(account_path, account_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
        ))
    acme = Acme(directory, account_key)
    try:
        account = acme.post(acme.directory["newAccount"], {"termsOfServiceAgreed": True})
        acme.kid = account.headers["Location"]
        order_response = acme.post(acme.directory["newOrder"], {"identifiers": [{"type": "dns", "value": host}]})
        order_url = order_response.headers["Location"]
        order = order_response.json()
        private_write(root / "operation.json", json.dumps({
            "order_url": order_url, "authorization_urls": order["authorizations"],
            "host": host, "directory": directory,
        }).encode())
        for authorization_url in order["authorizations"]:
            authorization = acme.post(authorization_url, None).json()
            if authorization["status"] == "valid":
                continue
            challenge = next(c for c in authorization["challenges"] if c["type"] == "dns-01")
            thumbprint = b64(hashlib.sha256(json.dumps(acme.jwk, sort_keys=True, separators=(",", ":")).encode()).digest())
            validation = b64(hashlib.sha256(f"{challenge['token']}.{thumbprint}".encode()).digest())
            add_txt(validation)
            deadline = time.monotonic() + 180
            while not txt_visible(validation):
                if time.monotonic() >= deadline:
                    raise TimeoutError("DNS-01 TXT record not publicly visible within 180 seconds.")
                time.sleep(5)
            acme.post(challenge["url"], {})
            acme.poll(authorization_url, {"valid"})
            remove_txt(validation)
        order = acme.poll(order_url, {"ready", "valid"})
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        csr = x509.CertificateSigningRequestBuilder().subject_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
        ).add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False).sign(key, hashes.SHA256())
        if order["status"] != "valid":
            acme.post(order["finalize"], {"csr": b64(csr.public_bytes(serialization.Encoding.DER))})
            order = acme.poll(order_url, {"valid"})
        certificate_bytes = acme.post(order["certificate"], None).content
        certificates = x509.load_pem_x509_certificates(certificate_bytes)
        pfx = pkcs12.serialize_key_and_certificates(
            host.encode(), key, certificates[0], certificates[1:], serialization.NoEncryption(),
        )
        private_write(root / "tls-key.pem", key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
        ))
        private_write(cert_path, certificate_bytes)
        private_write(pfx_path, pfx)
        return pfx_path
    finally:
        acme.http.close()
