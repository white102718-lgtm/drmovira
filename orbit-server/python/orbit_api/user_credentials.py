"""本地人员密码合同：只写、隐藏模型回显；幂等摘要按租户和操作使用密钥保护。"""

import re
import unicodedata

from pydantic import Field, SecretStr

from orbit_api.configuration import _parse_json
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.identity_contract import IdentityWrite, UserWrite, parse_identity_write


class LocalUserWrite(UserWrite):
    password: SecretStr = Field(exclude=True)


class PasswordReset(IdentityWrite):
    password: SecretStr = Field(exclude=True)


def checked_password(value):
    if not isinstance(value, str):
        raise OrbitError(400, "INVALID_STRUCTURE", "请填写登录密码", "/password")
    if (
        not 8 <= len(value) <= 64
        or not value.strip()
        or any(unicodedata.category(c).startswith("C") for c in value)
        or len(value.encode("utf-8")) > 72
    ):
        raise OrbitError(
            422,
            "PASSWORD_INVALID",
            "密码须为8至64个字符、UTF-8不超过72字节，不能包含控制字符",
            "/password",
        )
    return SecretStr(value)


def parse_local_user(raw):
    data = _parse_json(raw)
    if not isinstance(data, dict):
        raise OrbitError(400, "INVALID_STRUCTURE", "人员必须为对象")
    fields = dict(data)
    password = checked_password(fields.pop("password", None))
    value = parse_identity_write("USER", canonical(fields).encode())
    if value.status not in {"ENABLED", "DISABLED"}:
        raise OrbitError(422, "FIELD_INVALID", "请选择开启或停用", "/status")
    value.phone = re.sub(r"[\s-]", "", value.phone)
    if not re.fullmatch(r"\+?[0-9]{8,15}", value.phone):
        raise OrbitError(
            422, "PHONE_INVALID", "手机号作为登录账号，须为8至15位数字，可带国际区号", "/phone"
        )
    return LocalUserWrite(**value.model_dump(), password=password)


def parse_password_reset(raw):
    data = _parse_json(raw)
    if not isinstance(data, dict) or set(data) != {"password"}:
        raise OrbitError(400, "INVALID_STRUCTURE", "仅允许提交新登录密码")
    return PasswordReset(password=checked_password(data["password"]))


def secret_request_digest(tokens, operation, tenant, actor, fields, password, key_id):
    # 不用可离线猜测的无密钥SHA存储密码摘要，也不把密码塞进审计或幂等响应。
    return tokens.cipher.request_digest_internal(
        canonical([operation, tenant, actor, fields, password.get_secret_value()]).encode(), key_id
    )
