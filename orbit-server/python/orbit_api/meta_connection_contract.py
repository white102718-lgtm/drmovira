"""平台Meta读取应用与授权边界；客户端不能指定应用、回调或写入权限。"""

import base64
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import unquote, urlencode, urlsplit

CALLBACK = "https://drmovira.com/api/v1/integrations/meta/callback"


def return_path(value):
    """只接受站内页面；逐次解码阻止编码斜杠与控制字符重定向。"""
    if not isinstance(value, str) or not 1 <= len(value) <= 255:
        raise ValueError("站内返回路径无效")
    decoded = value
    for _ in range(5):
        if (
            not decoded.startswith("/")
            or decoded.startswith("//")
            or "\\" in decoded
            or any(ord(c) < 32 or ord(c) == 127 for c in decoded)
            or urlsplit(decoded).path.startswith("/api/")
        ):
            raise ValueError("站内返回路径无效")
        next_value = unquote(decoded)
        if next_value == decoded:
            return value
        decoded = next_value
    raise ValueError("站内返回路径编码过深")


@dataclass(frozen=True, repr=False)
class MetaApplication:
    """仅由服务端受控配置创建；密钥不参与repr与客户端响应。"""

    app_id: str
    app_secret: str
    graph_version: str
    login_config_id: str

    def __post_init__(self):
        from orbit_api.meta_read_contract import MetaReadFailure, validate_api_version

        try:
            validate_api_version(self.graph_version)
        except MetaReadFailure:
            raise ValueError("Meta Graph API版本尚未经过本适配器验收") from None
        if (
            not isinstance(self.app_id, str)
            or not isinstance(self.app_secret, str)
            or not isinstance(self.graph_version, str)
            or not isinstance(self.login_config_id, str)
            or not re.fullmatch(r"[0-9]{1,64}", self.app_id)
            or not re.fullmatch(r"v[0-9]{1,3}\.[0-9]{1,2}", self.graph_version)
            or not re.fullmatch(r"[0-9]{1,64}", self.login_config_id)
            or not self.app_secret
            or len(self.app_secret) > 1024
            or any(not 33 <= ord(c) <= 126 for c in self.app_secret)
        ):
            raise ValueError("Meta平台应用配置不完整")

    def authorize_url(self, state):
        return (
            "https://www.facebook.com/"
            + self.graph_version
            + "/dialog/oauth?"
            + urlencode(
                {
                    "client_id": self.app_id,
                    "redirect_uri": CALLBACK,
                    "state": state,
                    "response_type": "code",
                    "config_id": self.login_config_id,
                    "scope": "ads_read",
                    "override_default_response_type": "true",
                }
            )
        )


@dataclass(frozen=True)
class ValidatedGrant:
    principal_id: str
    scopes: tuple[str, ...]
    expires_at: datetime | None
    data_access_expires_at: datetime | None


def validate_grant(data, app, now, *, system_user=False):
    """debug_token证明应用、主体、权限和有效期；零有效期仅允许系统用户。"""
    if (
        not isinstance(data, dict)
        or data.get("is_valid") is not True
        or data.get("app_id") != app.app_id
        or not isinstance(data.get("user_id"), str)
        or not re.fullmatch(r"[0-9]{1,64}", data["user_id"])
        or not isinstance(data.get("scopes"), list)
        or len(data["scopes"]) > 200
        or any(
            not isinstance(scope, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,127}", scope)
            for scope in data["scopes"]
        )
        or "ads_read" not in data["scopes"]
    ):
        raise ValueError("Meta授权应用、主体或读取权限不符")
    deadlines = []
    for field in ("expires_at", "data_access_expires_at"):
        value = data.get(field)
        if system_user and type(value) is int and value == 0:
            deadlines.append(None)
        elif type(value) is int and now.timestamp() < value < 253402300800:
            deadlines.append(datetime.fromtimestamp(value, UTC))
        else:
            raise ValueError("Meta授权有效期无效")
    return ValidatedGrant(data["user_id"], tuple(sorted(set(data["scopes"]))), *deadlines)


def signed_request(value, secret, now):
    """取消授权/删除回调必须经过HMAC验证，原始签名正文不入日志。"""

    def decode(part):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", part):
            raise ValueError("签名编码无效")
        return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))

    try:
        if not isinstance(value, str) or len(value) > 16384:
            raise ValueError
        sig, body = value.split(".")
        if not hmac.compare_digest(
            decode(sig), hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
        ):
            raise ValueError
        from orbit_api.oidc_http import _constant, _object

        data = json.loads(decode(body), object_pairs_hook=_object, parse_constant=_constant)
        if (
            not isinstance(data, dict)
            or data.get("algorithm") != "HMAC-SHA256"
            or not re.fullmatch(r"[0-9]{1,64}", data.get("user_id", ""))
            or type(data.get("issued_at")) is not int
            or not -60 <= now.timestamp() - data["issued_at"] <= 600
        ):
            raise ValueError
        return data
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise ValueError("Meta回调签名无效或过期") from None


def selected_accounts(values):
    """仅接收最多500个唯一规范外部ID；存在性必须再由服务端候选验证。"""
    if (
        not isinstance(values, list)
        or not 1 <= len(values) <= 500
        or any(not isinstance(v, str) or not re.fullmatch(r"[0-9]{1,32}", v) for v in values)
        or len(set(values)) != len(values)
    ):
        raise ValueError("请选择1至500个不同的可访问账户")
    return tuple(values)
