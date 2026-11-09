"""有界签名游标与CSRF：绑定真实会话，不将JWT或凭据放入可读Token。"""

import base64
import hashlib
import hmac
import json
import time

from orbit_api.credentials import CredentialCipher
from orbit_api.errors import OrbitError


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class DirectoryTokens:
    def __init__(self, cipher: CredentialCipher):
        self.cipher = cipher

    def issue(self, purpose: str, claims: dict, ttl: int = 1800) -> str:
        from orbit_api.cookie_identity import current_cookie_identity

        identity = current_cookie_identity()
        if purpose == "DIRECTORY_CSRF_V1" and identity is not None:
            return identity.csrf_token
        payload = {**claims, "exp": int(time.time()) + ttl, "kid": self.cipher.active_key_id}
        raw = canonical(payload).encode()
        body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        return body + "." + self.cipher.application_mac(purpose, body.encode())

    def verify(self, purpose: str, token: str) -> dict:
        from orbit_api.cookie_identity import current_cookie_identity, verify_cookie_csrf

        identity = current_cookie_identity()
        if purpose == "DIRECTORY_CSRF_V1" and identity is not None:
            verify_cookie_csrf(identity.actor_id, token)
            return {"binding": self.session_binding("", identity.actor_id, identity.tenant_id)}
        try:
            if not isinstance(token, str) or len(token) > 2048:
                raise ValueError
            body, signature = token.split(".")
            raw = base64.b64decode(body + "=" * (-len(body) % 4), altchars=b"-_", validate=True)
            claims = json.loads(raw)
            if not isinstance(claims, dict) or canonical(claims).encode() != raw:
                raise ValueError
            if not isinstance(claims.get("kid"), str):
                raise ValueError
            mac = self.cipher.application_mac(purpose, body.encode(), claims["kid"])
            if not hmac.compare_digest(mac, signature):
                raise ValueError
            if type(claims.get("exp")) is not int or claims["exp"] <= int(time.time()):
                raise ValueError
            return claims
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise OrbitError(400, "TOKEN_INVALID", "游标或会话校验已失效，请重新加载") from None

    @staticmethod
    def session_binding(authorization: str, actor: int, tenant: str) -> str:
        from orbit_api.cookie_identity import current_cookie_identity

        identity = current_cookie_identity()
        if identity is not None:
            if actor != identity.actor_id or tenant != identity.tenant_id:
                raise OrbitError(401, "SESSION_REQUIRED", "当前会话身份不匹配")
            authorization = "COOKIE_SESSION:" + identity.session_id
        # 已有认证依赖先验证原Token；这里只保存不可逆摘要，不把Bearer签进公开数据。
        return hashlib.sha256(canonical([authorization, actor, tenant]).encode()).hexdigest()
