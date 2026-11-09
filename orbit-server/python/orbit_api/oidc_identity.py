"""验证受信发现文档所提供的RSA公钥，不从JWT头部加载远程密钥或推导业务权限。"""

import base64
import hmac
import json
import math
from dataclasses import dataclass

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from email_validator import EmailNotValidError, validate_email

from orbit_api.errors import OrbitError

_CLOCK_SKEW_SECONDS = 60


@dataclass(frozen=True, repr=False)
class VerifiedOidcIdentity:
    """仅包含验签后的身份要素；角色、团队和租户始终来自本地目录。"""

    issuer: str
    subject: str
    verified_email: str | None


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError
        value[key] = item
    return value


def _invalid_constant(_value):
    raise ValueError


def _jwt_object(segment):
    if not segment or any(
        char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
        for char in segment
    ):
        raise ValueError
    raw = base64.b64decode(segment + "=" * (-len(segment) % 4), altchars=b"-_", validate=True)
    value = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    if not isinstance(value, dict):
        raise ValueError
    return value


def _public_key(header, key_set):
    if not isinstance(key_set, dict) or not isinstance(key_set.get("keys"), list):
        raise ValueError
    if not 1 <= len(key_set["keys"]) <= 32:
        raise ValueError
    kid = header.get("kid")
    if kid is not None and (not isinstance(kid, str) or not 1 <= len(kid) <= 128):
        raise ValueError
    candidates = []
    for key in key_set["keys"]:
        if not isinstance(key, dict) or key.get("kty") != "RSA":
            continue
        if kid is not None and key.get("kid") != kid:
            continue
        if key.get("alg") not in {None, "RS256"} or key.get("use") not in {None, "sig"}:
            continue
        operations = key.get("key_ops")
        if operations is not None and operations != ["verify"]:
            continue
        if {"d", "p", "q", "dp", "dq", "qi", "oth"}.intersection(key):
            raise ValueError
        candidates.append(key)
    if len(candidates) != 1:
        raise ValueError
    public = jwt.PyJWK.from_dict(candidates[0], algorithm="RS256").key
    if not isinstance(public, rsa.RSAPublicKey) or not 2048 <= public.key_size <= 8192:
        raise ValueError
    return public


def _numeric_date(value):
    if type(value) not in {int, float} or not math.isfinite(value):
        raise ValueError
    return value


def verify_identity_token(
    token: str,
    key_set: dict,
    *,
    issuer: str,
    client_id: str,
    nonce: str,
    now: float,
    issued_after: float,
) -> VerifiedOidcIdentity:
    """固定RS256并校验issuer/aud/azp、nonce和时效；缺已验证邮箱不伪造验证证明。"""
    try:
        if not isinstance(token, str) or not 1 <= len(token) <= 16384:
            raise ValueError
        header_part, payload_part, signature = token.split(".")
        header = _jwt_object(header_part)
        _jwt_object(payload_part)  # 验签库默认允许重复JSON键，此处明确拒绝身份歧义。
        if not signature or header.get("alg") != "RS256":
            raise ValueError
        if any(name in header for name in ("jku", "jwk", "x5u", "crit", "b64")):
            raise ValueError
        if "typ" in header and (
            not isinstance(header["typ"], str) or header["typ"].upper() != "JWT"
        ):
            raise ValueError
        claims = jwt.decode(
            token,
            _public_key(header, key_set),
            algorithms=["RS256"],
            issuer=issuer,
            audience=client_id,
            options={
                "require": ["iss", "sub", "aud", "exp", "iat", "nonce"],
                "verify_exp": False,
                "verify_iat": False,
                "verify_nbf": False,
            },
        )
        subject = claims["sub"]
        if not isinstance(subject, str) or not 1 <= len(subject) <= 255:
            raise ValueError
        if not subject.isascii() or any(ord(char) < 32 or ord(char) == 127 for char in subject):
            raise ValueError
        audience = claims["aud"]
        if "azp" in claims and claims["azp"] != client_id:
            raise ValueError
        if isinstance(audience, list) and len(audience) > 1 and claims.get("azp") != client_id:
            raise ValueError
        token_nonce = claims["nonce"]
        if not isinstance(token_nonce, str) or not token_nonce.isascii():
            raise ValueError
        if not hmac.compare_digest(token_nonce, nonce):
            raise ValueError
        expires = _numeric_date(claims["exp"])
        issued = _numeric_date(claims["iat"])
        if expires <= now - _CLOCK_SKEW_SECONDS or issued > now + _CLOCK_SKEW_SECONDS:
            raise ValueError
        if issued < issued_after - _CLOCK_SKEW_SECONDS or expires <= issued:
            raise ValueError
        if "nbf" in claims and _numeric_date(claims["nbf"]) > now + _CLOCK_SKEW_SECONDS:
            raise ValueError
        email = claims.get("email")
        verified = claims.get("email_verified")
        if verified is not None and type(verified) is not bool:
            raise ValueError
        if email is not None:
            if not isinstance(email, str):
                raise ValueError
            email = validate_email(email, check_deliverability=False).normalized
        if verified is True and email is None:
            raise ValueError
        return VerifiedOidcIdentity(issuer, subject, email if verified is True else None)
    except (
        jwt.PyJWTError,
        ValueError,
        TypeError,
        KeyError,
        OverflowError,
        EmailNotValidError,
        RecursionError,
    ):
        # 不回显JWT、授权码、邮箱、密钥或底层验签错误，避免认证日志与响应泄露凭据。
        raise OrbitError(401, "OIDC_TOKEN_INVALID", "身份提供者返回的身份凭据校验失败") from None
