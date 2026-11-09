"""受信OIDC提供者客户端；不把提供者角色或任意回调参数当作业务授权。"""

import base64
import re
from dataclasses import dataclass
from urllib.parse import quote_plus, urlencode

from orbit_api.errors import OrbitError
from orbit_api.oidc_http import OidcHttp, secure_url
from orbit_api.oidc_identity import verify_identity_token


@dataclass(frozen=True, repr=False)
class ProviderConfiguration:
    issuer: str
    client_id: str
    redirect_uri: str
    client_secret: str


@dataclass(frozen=True)
class ProviderMetadata:
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    authentication_method: str


def _origin(parts):
    return parts.hostname.lower(), parts.port or 443


class OidcProvider:
    def __init__(self, configuration: ProviderConfiguration, *, http=None):
        self.configuration = configuration
        self.http = http or OidcHttp()
        issuer = secure_url(configuration.issuer)
        redirect = secure_url(configuration.redirect_uri)
        if (
            issuer.query
            or redirect.query
            or not isinstance(configuration.client_id, str)
            or not 1 <= len(configuration.client_id) <= 500
            or not isinstance(configuration.client_secret, str)
            or not 1 <= len(configuration.client_secret) <= 8192
            or any(ord(c) < 32 or ord(c) == 127 for c in configuration.client_id)
        ):
            raise OrbitError(503, "OIDC_CONFIGURATION_INVALID", "登录提供者配置不完整")
        self.origin = _origin(issuer)

    async def discover(self):
        document = await self.http.json(
            "GET", self.configuration.issuer.rstrip("/") + "/.well-known/openid-configuration"
        )
        try:
            if document.get("issuer") != self.configuration.issuer:
                raise ValueError
            required = {
                "response_types_supported": "code",
                "id_token_signing_alg_values_supported": "RS256",
                "code_challenge_methods_supported": "S256",
            }
            for field, supported in required.items():
                values = document.get(field)
                if not isinstance(values, list) or len(values) > 100 or supported not in values:
                    raise ValueError
            endpoints = []
            for field in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
                endpoint = document.get(field)
                parts = secure_url(endpoint)
                # 首期仅支持同issuer源端点；跨源CDN需以后显式受信配置，不能从发现文档放行任意URL。
                if _origin(parts) != self.origin or parts.query:
                    raise ValueError
                endpoints.append(endpoint)
            methods = document.get("token_endpoint_auth_methods_supported", ["client_secret_basic"])
            if not isinstance(methods, list) or len(methods) > 20:
                raise ValueError
            method = next(
                (m for m in ("client_secret_basic", "client_secret_post") if m in methods), None
            )
            if method is None:
                raise ValueError
            return ProviderMetadata(*endpoints, method)
        except (ValueError, OrbitError):
            raise OrbitError(
                502, "OIDC_DISCOVERY_INVALID", "登录提供者发现文档不符合要求"
            ) from None

    def authorization_url(self, metadata, state, nonce, challenge, *, choose_account=False):
        if not all(
            isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_-]{43}", v)
            for v in (state, nonce, challenge)
        ):
            raise ValueError("授权随机量无效")
        return (
            metadata.authorization_endpoint
            + "?"
            + urlencode(
                {
                    "response_type": "code",
                    "client_id": self.configuration.client_id,
                    "redirect_uri": self.configuration.redirect_uri,
                    "scope": "openid email",
                    "state": state,
                    "nonce": nonce,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    **({"prompt": "select_account"} if choose_account else {}),
                }
            )
        )

    async def exchange(self, metadata, code, verifier, *, nonce, now, issued_after):
        """授权码仅交换一次；只返回已验签身份，不保存或向调用方返回access/refresh token。"""
        if (
            not isinstance(code, str)
            or not 1 <= len(code) <= 2048
            or any(ord(c) < 32 or ord(c) == 127 for c in code)
            or not isinstance(verifier, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{43}", verifier)
        ):
            raise OrbitError(400, "OIDC_CALLBACK_INVALID", "登录回调参数无效")
        body = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": self.configuration.redirect_uri,
        }
        headers = [(b"Content-Type", b"application/x-www-form-urlencoded")]
        if metadata.authentication_method == "client_secret_basic":
            credentials = (
                quote_plus(self.configuration.client_id)
                + ":"
                + quote_plus(self.configuration.client_secret)
            ).encode()
            headers.append((b"Authorization", b"Basic " + base64.b64encode(credentials)))
        elif metadata.authentication_method == "client_secret_post":
            body.update(
                client_id=self.configuration.client_id,
                client_secret=self.configuration.client_secret,
            )
        else:
            raise OrbitError(503, "OIDC_CONFIGURATION_INVALID", "登录提供者认证方式不可用")
        tokens = await self.http.json(
            "POST", metadata.token_endpoint, headers=headers, content=urlencode(body).encode()
        )
        if "error" in tokens:
            raise OrbitError(401, "OIDC_EXCHANGE_FAILED", "登录授权码交换未通过")
        keys = await self.http.json("GET", metadata.jwks_uri)
        return verify_identity_token(
            tokens.get("id_token"),
            keys,
            issuer=self.configuration.issuer,
            client_id=self.configuration.client_id,
            nonce=nonce,
            now=now,
            issued_after=issued_after,
        )
