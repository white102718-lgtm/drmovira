"""人员、团队、功能角色的完整写入合同；原Schema不含的手机号单独登记扩展。"""

import json
from pathlib import Path
from typing import Literal
from uuid import UUID

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from orbit_api.configuration import _parse_json, short_text
from orbit_api.errors import OrbitError

_REGISTRY = json.loads(
    (Path(__file__).parent / "contracts/permission-registry.json").read_text(encoding="utf-8")
)


class IdentityWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class TeamWrite(IdentityWrite):
    name: str
    status: Literal["ENABLED", "DISABLED"]


class UserWrite(IdentityWrite):
    display_name: str
    nickname: str
    email: str
    phone: str = ""
    team_id: str
    role_ids: list[str] = Field(min_length=1, max_length=20)
    data_role: Literal["USER", "TEAM_ADMIN", "SUPER_ADMIN"]
    managed_team_ids: list[str] = Field(max_length=500)
    status: Literal["INVITED", "ENABLED", "DISABLED"]


class RoleWrite(IdentityWrite):
    name: str
    menu_codes: list[str] = Field(max_length=100)
    permission_codes: list[str] = Field(max_length=500)


def _uuid(value: str, pointer: str) -> str:
    try:
        result = str(UUID(value))
        if result != value.lower():
            raise ValueError
        return result
    except ValueError:
        raise OrbitError(422, "FIELD_INVALID", "请选择有效的业务UUID", pointer) from None


def _unique(values, pointer, normalize):
    result = []
    seen = set()
    for index, value in enumerate(values):
        item_pointer = f"{pointer}/{index}"
        normalized = normalize(value, item_pointer)
        if normalized in seen:
            raise OrbitError(422, "DUPLICATE_VALUE", "不能重复选择同一项", item_pointer)
        result.append(normalized)
        seen.add(normalized)
    # 这些字段为集合，顺序不产生角色优先级；规范顺序用于事务幂等摘要。
    return sorted(result)


def parse_identity_write(kind: Literal["USER", "TEAM", "ROLE"], raw: bytes):
    model = {"USER": UserWrite, "TEAM": TeamWrite, "ROLE": RoleWrite}[kind]
    data = _parse_json(raw)
    # Pydantic的Literal把数值/null也归为枚举值错误；产品区分结构400与字符串枚举422。
    if isinstance(data, dict):
        for field in ("status", "data_role"):
            if field in model.model_fields and field in data and not isinstance(data[field], str):
                raise OrbitError(400, "INVALID_STRUCTURE", "枚举字段必须是字符串", "/" + field)
    try:
        value = model.model_validate(data)
    except ValidationError as error:
        first = error.errors(include_input=False, include_context=False)[0]
        pointer = "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in first["loc"])
        if first["type"] == "extra_forbidden":
            raise OrbitError(400, "UNKNOWN_FIELD", "请求包含未定义字段", pointer) from None
        structure = first["type"] in {
            "missing",
            "string_type",
            "list_type",
            "model_type",
            "model_attributes_type",
        }
        raise OrbitError(
            400 if structure else 422,
            "INVALID_STRUCTURE" if structure else "FIELD_INVALID",
            "请求字段结构无效" if structure else "字段值或数量不符合要求",
            pointer,
        ) from None
    if isinstance(value, TeamWrite):
        value.name = short_text(value.name, 100, "/name")
    elif isinstance(value, UserWrite):
        value.display_name = short_text(value.display_name, 50, "/display_name")
        value.nickname = short_text(value.nickname, 50, "/nickname", required=False)
        value.phone = short_text(value.phone, 32, "/phone", required=False)
        value.email = short_text(value.email, 254, "/email")
        try:
            value.email = validate_email(value.email, check_deliverability=False).normalized
        except EmailNotValidError:
            raise OrbitError(422, "EMAIL_INVALID", "请输入格式正确的邮箱", "/email") from None
        value.team_id = _uuid(value.team_id, "/team_id")
        value.role_ids = _unique(value.role_ids, "/role_ids", _uuid)
        value.managed_team_ids = _unique(value.managed_team_ids, "/managed_team_ids", _uuid)
        if value.data_role == "USER" and value.managed_team_ids:
            raise OrbitError(
                422, "DATA_SCOPE_INVALID", "普通用户不能拥有团队管理范围", "/managed_team_ids"
            )
    else:
        value.name = short_text(value.name, 50, "/name")

        def registered(registry_key, maximum):
            def normalize(item, pointer):
                item = short_text(item, maximum, pointer)
                if item not in _REGISTRY[registry_key]:
                    raise OrbitError(
                        422, "PERMISSION_UNKNOWN", "只能选择当前注册的菜单或动作", pointer
                    )
                return item

            return normalize

        value.menu_codes = _unique(value.menu_codes, "/menu_codes", registered("menus", 64))
        value.permission_codes = _unique(
            value.permission_codes, "/permission_codes", registered("permissions", 100)
        )
        # 不强制单一角色同时拥有菜单和动作；多角色的菜单/动作并集仍需服务端求交校验。
    return value
