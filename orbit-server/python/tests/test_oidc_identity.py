"""用动态RSA密钥实际签名，验证OIDC身份而不是模拟验签成功。"""

import base64
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from orbit_api.errors import OrbitError
from orbit_api.oidc_identity import verify_identity_token

ISSUER = "https://idp.fixture.example"
CLIENT = "orbit-fixture-client"
NONCE = "one-use-fixture-authorization-nonce"


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def claims(**changes):
    now = int(time.time())
    return {
        "iss": ISSUER,
        "sub": "issuer-local-subject",
        "aud": CLIENT,
        "nonce": NONCE,
        "iat": now,
        "exp": now + 300,
        "email": "User@EXAMPLE.ORG",
        "email_verified": True,
    } | changes


def key_set(key):
    return {
        "keys": [
            json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
            | {"kid": "v1", "use": "sig", "alg": "RS256"}
        ]
    }


def verify(token, keys):
    now = time.time()
    return verify_identity_token(
        token, keys, issuer=ISSUER, client_id=CLIENT, nonce=NONCE, now=now, issued_after=now - 30
    )


def token(key, payload=None, **headers):
    # 独立构造实际JWS；编码库会省略默认b64:true，不能误以为该负例真的带了该字段。
    return signed_raw(
        key,
        json.dumps({"alg": "RS256", "typ": "JWT", "kid": "v1"} | headers).encode(),
        json.dumps(payload or claims()).encode(),
    )


def signed_raw(key, header, payload):
    def encode(value):
        return base64.urlsafe_b64encode(value).rstrip(b"=")

    message = encode(header) + b"." + encode(payload)
    signature = key.sign(message, padding.PKCS1v15(), hashes.SHA256())
    return (message + b"." + encode(signature)).decode()


def test_identity_signature_email_and_permission_separation(signing_key):
    value = verify(
        token(signing_key, claims(tenant_id="forged", roles=["SUPER_ADMIN"])), key_set(signing_key)
    )
    assert value.issuer == ISSUER and value.subject == "issuer-local-subject"
    assert value.verified_email == "User@example.org"
    assert not hasattr(value, "roles") and not hasattr(value, "tenant_id")
    assert "issuer-local-subject" not in repr(value) and "User@example.org" not in repr(value)


def test_missing_or_false_verification_never_becomes_verified_email(signing_key):
    for verified in (None, False):
        value = claims()
        if verified is None:
            value.pop("email_verified")
        else:
            value["email_verified"] = verified
        assert verify(token(signing_key, value), key_set(signing_key)).verified_email is None


@pytest.mark.parametrize(
    "change",
    [
        {"iss": ISSUER + "/"},
        {"aud": "another-client"},
        {"nonce": "another-flow"},
        {"nonce": 1},
        {"sub": ""},
        {"sub": "x" * 256},
        {"sub": "非ASCII"},
        {"sub": True},
        {"email_verified": "true"},
        {"email_verified": 1},
        {"email": []},
        {"email": "invalid"},
        {"email": None, "email_verified": True},
        {"iat": True},
        {"exp": False},
        {"iat": float("inf")},
        {"unused": float("nan")},
        {"aud": [CLIENT, "other"]},
        {"aud": [CLIENT, "other"], "azp": "other"},
        {"azp": "other"},
    ],
)
def test_invalid_signed_identity_claims_are_rejected_without_input_disclosure(signing_key, change):
    raw = token(signing_key, claims(**change))
    with pytest.raises(OrbitError) as error:
        verify(raw, key_set(signing_key))
    assert error.value.status == 401 and error.value.code == "OIDC_TOKEN_INVALID"
    assert raw not in str(error.value) and error.value.__cause__ is None


@pytest.mark.parametrize(
    "change",
    [
        {"exp": -300},
        {"iat": 300},
        {"iat": -300},
        {"nbf": 300},
    ],
)
def test_expiry_future_issue_and_state_freshness_are_checked(signing_key, change):
    now = int(time.time())
    payload = claims(**{field: now + delta for field, delta in change.items()})
    with pytest.raises(OrbitError):
        verify(token(signing_key, payload), key_set(signing_key))


def test_multiple_audiences_require_matching_authorized_party(signing_key):
    value = verify(
        token(signing_key, claims(aud=[CLIENT, "other"], azp=CLIENT)), key_set(signing_key)
    )
    assert value.subject == "issuer-local-subject"


@pytest.mark.parametrize(
    "header",
    [
        {"jku": "https://untrusted.example/key"},
        {"jwk": {}},
        {"x5u": "https://untrusted.example/cert"},
        {"crit": []},
        {"b64": True},
        {"typ": "at+jwt"},
        {"kid": "unknown"},
    ],
)
def test_jwt_headers_cannot_select_remote_keys_or_token_type(signing_key, header):
    with pytest.raises(OrbitError):
        verify(token(signing_key, **header), key_set(signing_key))


def test_signature_algorithm_and_ambiguous_keys_are_rejected(signing_key):
    payload = claims()
    for raw in (
        jwt.encode(payload, "untrusted-symmetric-key-material-for-fixture", algorithm="HS256"),
        jwt.encode(payload, "", algorithm="none"),
    ):
        with pytest.raises(OrbitError):
            verify(raw, key_set(signing_key))
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(OrbitError):
        verify(token(other), key_set(signing_key))
    duplicate = key_set(signing_key)
    duplicate["keys"] *= 2
    with pytest.raises(OrbitError):
        verify(token(signing_key), duplicate)


def test_signed_duplicate_claims_are_rejected_instead_of_accepting_last_value(signing_key):
    def encode(value):
        return base64.urlsafe_b64encode(value).rstrip(b"=")

    header = encode(b'{"alg":"RS256","kid":"v1"}')
    payload = (
        json.dumps(claims())
        .replace('"sub": "issuer-local-subject"', '"sub":"first","sub":"issuer-local-subject"')
        .encode()
    )
    message = header + b"." + encode(payload)
    signature = signing_key.sign(message, padding.PKCS1v15(), hashes.SHA256())
    raw = (message + b"." + encode(signature)).decode()
    with pytest.raises(OrbitError):
        verify(raw, key_set(signing_key))
