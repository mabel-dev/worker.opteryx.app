import json
import os
import sys

sys.path.insert(0, os.getcwd())

import asyncio
from starlette.requests import Request as StarletteRequest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
from jose import jwt as jose_jwt

from app.routes.v1 import interface as interface_module
from app import auth as auth_module
from fastapi import HTTPException
from app import secret_store as secret_store_module
from app.main import app as fastapi_app
from starlette.testclient import TestClient


def _generate_rsa_keypair() -> tuple[str, str]:
    """Generate an RSA keypair and return (priv_pem, pub_pem).

    The keys are returned as PEM-encoded strings suitable for jose.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    priv_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    pub_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return priv_pem, pub_pem


def _make_request(body: bytes, headers: list[tuple[bytes, bytes]]):
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/submit",
        "headers": headers,
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return StarletteRequest(scope, receive)


def test_submit_valid_gpc_token(monkeypatch):
    kid = "testkid"
    expected_sub = "109805708368864229943"
    priv_pem, pub_pem = _generate_rsa_keypair()

    # Monkeypatch secret_store.load_public_key to return our generated public key
    monkeypatch.setattr(
        secret_store_module, "load_public_key", lambda k: pub_pem if k == kid else None
    )

    payload = {
        "sub": expected_sub,
        "aud": auth_module.EXPECTED_AUDIENCE,
        "iss": auth_module.EXPECTED_ISSUER,
    }
    token = jose_jwt.encode(payload, priv_pem, algorithm="RS256", headers={"kid": kid})
    req = _make_request(
        json.dumps({"statementHandle": "abcd"}).encode(),
        [(b"authorization", f"Bearer {token}".encode()), (b"content-type", b"application/json")],
    )
    # Call the async endpoint directly
    res = asyncio.get_event_loop().run_until_complete(interface_module.submit(req))
    data = res
    assert data.get("accepted") is True
    assert data.get("job") == "abcd"
    assert data.get("jwt_sub") == expected_sub


def test_submit_invalid_sub(monkeypatch):
    # Create request and call endpoint directly; avoid TestClient to keep deps simple
    kid = "testkid"
    priv_pem, pub_pem = _generate_rsa_keypair()

    monkeypatch.setattr(
        secret_store_module, "load_public_key", lambda k: pub_pem if k == kid else None
    )

    # Create a token with a different subject
    payload = {
        "sub": "different-sub",
        "aud": auth_module.EXPECTED_AUDIENCE,
        "iss": auth_module.EXPECTED_ISSUER,
    }
    token = jose_jwt.encode(payload, priv_pem, algorithm="RS256", headers={"kid": kid})
    req = _make_request(
        json.dumps({"statementHandle": "abcd"}).encode(),
        [(b"authorization", f"Bearer {token}".encode()), (b"content-type", b"application/json")],
    )
    # endpoint should raise HTTPException which will propagate as exception
    try:
        asyncio.get_event_loop().run_until_complete(interface_module.submit(req))
        assert False, "Expected HTTPException for invalid subject"
    except HTTPException:
        pass


def test_validate_token_helper_invalid_audience(monkeypatch):
    kid = "testkid"
    priv_pem, pub_pem = _generate_rsa_keypair()

    monkeypatch.setattr(
        secret_store_module, "load_public_key", lambda k: pub_pem if k == kid else None
    )

    # Use a different audience than expected
    payload = {
        "sub": auth_module.GPC_SUBJECT,
        "aud": "https://fraud.example",
        "iss": auth_module.EXPECTED_ISSUER,
    }
    token = jose_jwt.encode(payload, priv_pem, algorithm="RS256", headers={"kid": kid})
    try:
        auth_module.validate_token(token)
        assert False, "Expected HTTPException for invalid audience"
    except HTTPException:
        pass


def test_validate_token_helper_invalid_issuer(monkeypatch):
    kid = "testkid"
    priv_pem, pub_pem = _generate_rsa_keypair()

    monkeypatch.setattr(
        secret_store_module, "load_public_key", lambda k: pub_pem if k == kid else None
    )

    # Use a different issuer than expected
    payload = {
        "sub": auth_module.GPC_SUBJECT,
        "aud": auth_module.EXPECTED_AUDIENCE,
        "iss": "https://evil.example",
    }
    token = jose_jwt.encode(payload, priv_pem, algorithm="RS256", headers={"kid": kid})
    try:
        auth_module.validate_token(token)
        assert False, "Expected HTTPException for invalid issuer"
    except HTTPException:
        pass


def test_submit_missing_token():
    req = _make_request(
        json.dumps({"statementHandle": "abcd"}).encode(),
        [(b"content-type", b"application/json")],
    )
    try:
        asyncio.get_event_loop().run_until_complete(interface_module.submit(req))
        assert False, "Expected HTTPException for missing token"
    except HTTPException:
        pass


def test_validate_token_helper(monkeypatch):
    kid = "testkid"
    expected_sub = "109805708368864229943"
    priv_pem, pub_pem = _generate_rsa_keypair()

    monkeypatch.setattr(
        secret_store_module, "load_public_key", lambda k: pub_pem if k == kid else None
    )

    payload = {
        "sub": expected_sub,
        "aud": auth_module.EXPECTED_AUDIENCE,
        "iss": auth_module.EXPECTED_ISSUER,
    }
    token = jose_jwt.encode(payload, priv_pem, algorithm="RS256", headers={"kid": kid})
    claims = auth_module.validate_token(token)
    assert claims.get("sub") == expected_sub


def test_validate_token_helper_invalid_sub(monkeypatch):
    kid = "testkid"
    priv_pem, pub_pem = _generate_rsa_keypair()

    monkeypatch.setattr(
        secret_store_module, "load_public_key", lambda k: pub_pem if k == kid else None
    )

    payload = {
        "sub": "different-sub",
        "aud": auth_module.EXPECTED_AUDIENCE,
        "iss": auth_module.EXPECTED_ISSUER,
    }
    token = jose_jwt.encode(payload, priv_pem, algorithm="RS256", headers={"kid": kid})
    try:
        auth_module.validate_token(token)
        assert False, "Expected HTTPException for invalid subject"
    except HTTPException:
        pass


def test_audit_middleware_receives_audit_payload(monkeypatch):
    kid = "testkid"
    expected_sub = "109805708368864229943"
    priv_pem, pub_pem = _generate_rsa_keypair()

    # Monkeypatch secret_store.load_public_key to return our generated public key
    monkeypatch.setattr(
        secret_store_module, "load_public_key", lambda k: pub_pem if k == kid else None
    )

    payload = {
        "sub": expected_sub,
        "aud": auth_module.EXPECTED_AUDIENCE,
        "iss": auth_module.EXPECTED_ISSUER,
    }
    token = jose_jwt.encode(payload, priv_pem, algorithm="RS256", headers={"kid": kid})

    # Prevent heavy work in worker.process_statement
    monkeypatch.setattr("app.worker.process_statement", lambda handle: None)

    captured = {}

    class FakeLogger:
        def audit(self, p):
            captured["payload"] = p

        def error(self, *_a, **_k):
            pass

    monkeypatch.setattr("app.middleware.audit.logger", FakeLogger(), raising=False)

    # Use TestClient to go through the full middleware stack
    client = TestClient(fastapi_app)
    res = client.post(
        "/api/v1/submit",
        json={"statementHandle": "abcd"},
        headers={"authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    # The middleware should have captured the response 'audit' object
    assert "payload" in captured
    assert captured["payload"].get("path") == "/api/v1/submit"
    assert captured["payload"].get("response_audit") == {"job": "abcd", "jwt_sub": expected_sub}
