from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

sys.path.insert(0, str(Path(__file__).resolve().parent))
from certificate import Acme


def decode(value):
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def test_acme_signs_target_payload_and_refreshes_bad_nonce_once():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    posts = []

    def transport(request):
        if request.method == "GET":
            return httpx.Response(200, json={"newNonce": "https://ca.test/nonce", "newAccount": "https://ca.test/account"})
        if request.method == "HEAD":
            return httpx.Response(200, headers={"Replay-Nonce": "nonce-1"})
        body = json.loads(request.content)
        protected = json.loads(decode(body["protected"]))
        key.public_key().verify(
            decode(body["signature"]), f"{body['protected']}.{body['payload']}".encode(),
            padding.PKCS1v15(), hashes.SHA256(),
        )
        assert protected["url"] == "https://ca.test/account"
        assert protected["alg"] == "RS256"
        assert json.loads(decode(body["payload"])) == {"termsOfServiceAgreed": True}
        posts.append(protected)
        if len(posts) == 1:
            return httpx.Response(400, headers={"Replay-Nonce": "nonce-2"}, json={"type": "urn:ietf:params:acme:error:badNonce"})
        return httpx.Response(201, headers={"Location": "https://ca.test/account/1", "Replay-Nonce": "nonce-3"}, json={})

    real_client = httpx.Client
    with patch("certificate.httpx.Client", side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(transport), **kwargs)):
        acme = Acme("https://ca.test/directory", key)
        response = acme.post(acme.directory["newAccount"], {"termsOfServiceAgreed": True})
        assert response.status_code == 201
        assert [item["nonce"] for item in posts] == ["nonce-1", "nonce-2"]
        acme.http.close()


def test_invalid_acme_authorization_is_not_success():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    real_client = httpx.Client

    def transport(request):
        if request.method == "GET":
            return httpx.Response(200, json={"newNonce": "https://ca.test/nonce"})
        if request.method == "HEAD":
            return httpx.Response(200, headers={"Replay-Nonce": "nonce"})
        return httpx.Response(200, json={
            "status": "invalid",
            "challenges": [{"error": {"type": "dns", "detail": "TXT record not visible"}}],
        })

    with patch("certificate.httpx.Client", side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(transport), **kwargs)):
        acme = Acme("https://ca.test/directory", key)
        with pytest.raises(RuntimeError, match="TXT record not visible"):
            acme.poll("https://ca.test/authorization/1", {"valid"})
        acme.http.close()
