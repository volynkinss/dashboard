import asyncio
import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
project_root_value = str(PROJECT_ROOT)
if project_root_value not in sys.path:
    sys.path.insert(0, project_root_value)

from app.security.oidc import KeycloakOIDCClient, OIDCError


ISSUER = "https://keycloak.example.internal/realms/company"
KEY_ID = "test-key"


def _build_client(public_jwk: dict, *, metadata_algorithms: list[str]) -> KeycloakOIDCClient:
    settings = SimpleNamespace(
        keycloak_issuer_url=ISSUER,
        keycloak_client_id="catalog",
        keycloak_client_secret="secret",
        roles_client_id="catalog",
    )
    client = KeycloakOIDCClient(settings)
    client._metadata = {
        "issuer": ISSUER,
        "jwks_uri": f"{ISSUER}/protocol/openid-connect/certs",
        "id_token_signing_alg_values_supported": metadata_algorithms,
    }
    client._jwks = {"keys": [public_jwk]}
    return client


def _rsa_key_pair() -> tuple[object, dict]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk.update({"kid": KEY_ID, "alg": "RS256", "use": "sig"})
    return private_key, public_jwk


def _token_claims(**overrides) -> dict:
    now = datetime.now(timezone.utc)
    claims = {
        "iss": ISSUER,
        "sub": "user-1",
        "aud": "catalog",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    claims.update(overrides)
    return claims


def _at_hash(access_token: str, algorithm_name: str = "RS256") -> str:
    algorithm = jwt.get_algorithm_by_name(algorithm_name)
    digest = algorithm.compute_hash_digest(access_token.encode("ascii"))
    return base64.urlsafe_b64encode(digest[: len(digest) // 2]).rstrip(b"=").decode("ascii")


def test_decode_token_accepts_rs256_and_valid_at_hash():
    private_key, public_jwk = _rsa_key_pair()
    client = _build_client(public_jwk, metadata_algorithms=["RS256", "ES256"])
    access_token = "access-token"
    token = jwt.encode(
        _token_claims(at_hash=_at_hash(access_token)),
        private_key,
        algorithm="RS256",
        headers={"kid": KEY_ID},
    )

    claims = asyncio.run(
        client._decode_token(
            token,
            audience="catalog",
            verify_audience=True,
            access_token=access_token,
        )
    )

    assert claims["sub"] == "user-1"


def test_decode_token_rejects_invalid_at_hash():
    private_key, public_jwk = _rsa_key_pair()
    client = _build_client(public_jwk, metadata_algorithms=["RS256"])
    token = jwt.encode(
        _token_claims(at_hash="invalid"),
        private_key,
        algorithm="RS256",
        headers={"kid": KEY_ID},
    )

    with pytest.raises(OIDCError, match="at_hash claim does not match access token"):
        asyncio.run(
            client._decode_token(
                token,
                audience="catalog",
                verify_audience=True,
                access_token="access-token",
            )
        )


def test_decode_token_rejects_at_hash_without_access_token():
    private_key, public_jwk = _rsa_key_pair()
    client = _build_client(public_jwk, metadata_algorithms=["RS256"])
    token = jwt.encode(
        _token_claims(at_hash="present"),
        private_key,
        algorithm="RS256",
        headers={"kid": KEY_ID},
    )

    with pytest.raises(OIDCError, match="Unable to verify at_hash claim"):
        asyncio.run(client._decode_token(token, audience="catalog", verify_audience=True))


def test_decode_token_rejects_invalid_audience():
    private_key, public_jwk = _rsa_key_pair()
    client = _build_client(public_jwk, metadata_algorithms=["RS256"])
    token = jwt.encode(
        _token_claims(aud="another-client"),
        private_key,
        algorithm="RS256",
        headers={"kid": KEY_ID},
    )

    with pytest.raises(OIDCError, match="Audience doesn't match"):
        asyncio.run(client._decode_token(token, audience="catalog", verify_audience=True))


def test_decode_token_preserves_future_iat_compatibility():
    private_key, public_jwk = _rsa_key_pair()
    client = _build_client(public_jwk, metadata_algorithms=["RS256"])
    token = jwt.encode(
        _token_claims(iat=datetime.now(timezone.utc) + timedelta(seconds=30)),
        private_key,
        algorithm="RS256",
        headers={"kid": KEY_ID},
    )

    claims = asyncio.run(client._decode_token(token, audience="catalog", verify_audience=True))

    assert claims["sub"] == "user-1"


def test_decode_token_rejects_es256_even_when_provider_advertises_it():
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_jwk = ECAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk.update({"kid": KEY_ID, "alg": "ES256", "use": "sig"})
    client = _build_client(public_jwk, metadata_algorithms=["RS256", "ES256"])
    token = jwt.encode(
        _token_claims(),
        private_key,
        algorithm="ES256",
        headers={"kid": KEY_ID},
    )

    with pytest.raises(OIDCError, match="Unsupported token signing algorithm: ES256"):
        asyncio.run(client._decode_token(token, audience="catalog", verify_audience=True))
