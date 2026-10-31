"""Entra v2 access tokens only. Key URLs derive from pinned tenant, never token."""
import hashlib
import jwt
from fastapi import HTTPException


class EntraAuth:
    def __init__(self, tenant, audience, allowed_object_ids, key_client=None):
        self.tenant = tenant
        self.audience = audience
        self.allowed = frozenset(allowed_object_ids)
        if not self.allowed:
            raise ValueError("Object ID allowlist required")
        self.issuer = f"https://login.microsoftonline.com/{tenant}/v2.0"
        self.keys = key_client or jwt.PyJWKClient(
            f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys",
            cache_jwk_set=True, lifespan=3600, timeout=5,
        )

    def __call__(self, authorization):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "Bearer access token required", headers={"WWW-Authenticate": "Bearer"})
        token = authorization[7:]
        if len(token) > 16384:
            raise HTTPException(401, "Invalid access token")
        try:
            key = self.keys.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256"], audience=self.audience,
                                issuer=self.issuer,
                                options={"require": ["exp", "iat", "nbf", "iss", "aud", "tid", "oid"]})
            if claims["tid"] != self.tenant or not isinstance(claims["oid"], str):
                raise ValueError("Tenant or subject mismatch")
            # Require delegated user permission. ID tokens and app-only tokens are not this UI's API contract.
            if "access_as_user" not in claims.get("scp", "").split():
                raise ValueError("Delegated scope required")
            if claims["oid"] not in self.allowed:
                raise ValueError("User not authorized")
            return hashlib.sha256(f"{self.tenant}:{claims['oid']}".encode()).hexdigest()
        except Exception:
            raise HTTPException(401, "Invalid access token", headers={"WWW-Authenticate": "Bearer"}) from None
