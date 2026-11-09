"""OIDC公开请求合同：保留原AuthorizationStart，不接受浏览器注入身份或租户。"""

import hashlib
import re
import secrets
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from orbit_api.configuration import _parse_json, short_text
from orbit_api.errors import OrbitError

SESSION_COOKIE = "adpilot_session"
IDLE_SECONDS = 30 * 60
ABSOLUTE_SECONDS = 12 * 60 * 60
AUTHORIZATION_SECONDS = 5 * 60
INVITATION_SECONDS = 24 * 60 * 60
_OPAQUE = re.compile(r"[A-Za-z0-9_-]{43}\Z")
_PURPOSES = {"SESSION", "AUTHORIZATION_STATE", "BROWSER_BINDING", "INVITATION"}


@dataclass(frozen=True)
class AuthorizationStart:
    return_to: str


@dataclass(frozen=True, repr=False)
class InvitationAuthorizationStart:
    invitation_token: str
    return_to: str


def safe_return_to(value: str) -> str:
    """只允许同站相对路径；对嵌套编码再次检查，避免浏览器把反斜线或双斜线当外站。"""
    value = short_text(value, 255, "/return_to")
    if re.search(r"%(?![0-9A-Fa-f]{2})", value):
        raise OrbitError(422, "FIELD_INVALID", "返回地址编码无效", "/return_to")
    candidate = value
    try:
        for _ in range(8):
            short_text(candidate, 4096, "/return_to")
            parts = urlsplit(candidate)
            if (
                not candidate.startswith("/")
                or candidate.startswith("//")
                or "\\" in candidate
                or parts.scheme
                or parts.netloc
            ):
                raise ValueError
            decoded = unquote(candidate, errors="strict")
            if decoded == candidate:
                return value
            candidate = decoded
    except (ValueError, UnicodeError):
        pass
    raise OrbitError(422, "FIELD_INVALID", "返回地址必须是站内路径", "/return_to")


def parse_authorization_start(raw: bytes) -> AuthorizationStart:
    """重复键、未知字段、错误类型和有界正文均在发起外部请求前拒绝。"""
    if len(raw) > 4096:
        raise OrbitError(413, "BODY_TOO_LARGE", "登录请求正文过大")
    try:
        value = _parse_json(raw)
    except RecursionError:
        raise OrbitError(400, "INVALID_STRUCTURE", "请求JSON层级过深") from None
    if not isinstance(value, dict):
        raise OrbitError(400, "INVALID_STRUCTURE", "登录请求必须是JSON对象")
    extra = set(value) - {"return_to"}
    if extra:
        raise OrbitError(400, "UNKNOWN_FIELD", "请求包含未知字段")
    if set(value) != {"return_to"} or not isinstance(value["return_to"], str):
        raise OrbitError(400, "INVALID_STRUCTURE", "登录请求仅接受返回地址字符串")
    return AuthorizationStart(safe_return_to(value["return_to"]))


def opaque_token() -> str:
    """256位随机不透明凭据；不使用可预测UUID作为浏览器会话或邀请凭据。"""
    return secrets.token_urlsafe(32)


def parse_invitation_authorization_start(raw: bytes) -> InvitationAuthorizationStart:
    """单独扩展邀请授权正文；不在原AuthorizationStart混入身份或凭据字段。"""
    if len(raw) > 4096:
        raise OrbitError(413, "BODY_TOO_LARGE", "邀请授权请求正文超过上限")
    try:
        value = _parse_json(raw)
    except RecursionError:
        raise OrbitError(400, "INVALID_STRUCTURE", "邀请授权请求结构无效") from None
    if (
        not isinstance(value, dict)
        or set(value) != {"invitation_token", "return_to"}
        or not isinstance(value["invitation_token"], str)
        or not isinstance(value["return_to"], str)
    ):
        raise OrbitError(400, "INVALID_STRUCTURE", "邀请授权仅接受邀请凭据与返回地址")
    try:
        credential_digest("INVITATION", value["invitation_token"])
    except OrbitError:
        raise OrbitError(401, "INVITATION_INVALID", "邀请凭据无效或已过期") from None
    return InvitationAuthorizationStart(
        value["invitation_token"], safe_return_to(value["return_to"])
    )


def credential_digest(purpose: str, value: str) -> bytes:
    """存储不可逆且分用途的摘要，防止把邀请凭据误用成会话凭据。"""
    if purpose not in _PURPOSES:
        raise ValueError("未知认证凭据用途")
    if not isinstance(value, str) or not _OPAQUE.fullmatch(value):
        raise OrbitError(401, "SESSION_REQUIRED", "认证凭据无效或已过期")
    return hashlib.sha256(("ORBIT_" + purpose + "_V1:" + value).encode("ascii")).digest()
