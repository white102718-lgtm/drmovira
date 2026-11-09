"""配置公开字段接口：复用真实Python若依认证，授权从当前业务数据库复核。"""

from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from config.orbit_runtime import private_values
from fastapi import APIRouter, Depends, Request
from module_admin.entity.vo.user_vo import CurrentUserModel

from orbit_api.authorization import require_configuration_access
from orbit_api.configuration import metadata, parse_probe_reason, parse_write
from orbit_api.configuration_store import ConfigurationStore
from orbit_api.connection_probe import ModelConnectionProbe
from orbit_api.credentials import CredentialCipher
from orbit_api.errors import OrbitError
from orbit_api.material_scanner_registry import scanner_registry

router = APIRouter(prefix="/api/v1/system-configurations", tags=["ORBIT系统配置"])


def model_probe() -> ModelConnectionProbe:
    return ModelConnectionProbe()


def credential_cipher() -> CredentialCipher:
    import json

    values = private_values()
    try:
        keys = values.get("ORBIT_PYTHON_SECRETS_KEYS", {})
        if isinstance(keys, str):
            keys = json.loads(keys)
        if not isinstance(keys, dict):
            raise ValueError
        return CredentialCipher(
            values.get("ORBIT_PYTHON_SECRETS_ACTIVE_KEY_ID"),
            keys,
            forbidden_material=(str(values.get("ORBIT_PYTHON_JWT_SECRET_KEY", "")).encode(),),
        )
    except OrbitError:
        raise
    except Exception:
        raise OrbitError(503, "KEY_CONFIGURATION_INVALID", "服务端独立主密钥配置无效") from None


@router.get("/metadata")
async def configuration_metadata(
    request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    if request.query_params:
        raise OrbitError(400, "UNKNOWN_FIELD", "此接口不接受查询参数")
    if "x-target-tenant" in request.headers:
        raise OrbitError(403, "PERMISSION_DENIED", "此接口不接受指定租户")
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        await require_configuration_access(session, user.user.user_id)
    return {"sections": metadata(), "encryptionReady": credential_cipher().ready}


def _headers(request: Request, updating: bool) -> tuple[str, int]:
    import re

    if request.query_params:
        raise OrbitError(400, "UNKNOWN_FIELD", "此接口不接受查询参数")
    if "x-target-tenant" in request.headers:
        raise OrbitError(403, "PERMISSION_DENIED", "此接口不接受指定租户")
    keys = request.headers.getlist("idempotency-key")
    if len(keys) != 1 or not re.fullmatch(r"[A-Za-z0-9:_-]{8,128}", keys[0]):
        raise OrbitError(400, "IDEMPOTENCY_REQUIRED", "请提供有效且唯一的幂等键")
    revisions = request.headers.getlist("if-match")
    if not updating:
        if revisions:
            raise OrbitError(400, "INVALID_REQUEST", "新建配置不能指定已有版本")
        return keys[0], 0
    if len(revisions) != 1 or not re.fullmatch(r'"[1-9][0-9]{0,17}"', revisions[0]):
        raise OrbitError(400, "REVISION_REQUIRED", "请提供带引号的配置版本")
    return keys[0], int(revisions[0][1:-1])


@router.get("")
async def list_configurations(
    request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await ConfigurationStore(credential_cipher()).list(session, user.user.user_id)


@router.get("/material-scanner-profiles")
async def material_scanner_profiles(
    request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        await require_configuration_access(session, user.user.user_id)
    return {"items": scanner_registry(request).candidates()}


@router.get("/{config_id}")
async def get_configuration(
    config_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    _read_boundary(request)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await ConfigurationStore(credential_cipher()).get(
            session, user.user.user_id, config_id
        )


def _read_boundary(request: Request, allowed: set[str] | None = None):
    if set(request.query_params) - (allowed or set()):
        raise OrbitError(400, "UNKNOWN_FIELD", "此接口不接受该查询参数")
    if "x-target-tenant" in request.headers:
        raise OrbitError(403, "PERMISSION_DENIED", "此接口不接受指定租户")
    for key in request.query_params:
        if len(request.query_params.getlist(key)) != 1:
            raise OrbitError(400, "INVALID_STRUCTURE", "查询参数不能重复")


@router.get("/{config_id}/history")
async def configuration_history(
    config_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    import re

    _read_boundary(request, {"beforeRevision", "pageSize"})
    before, size = None, 50
    for key, value in request.query_params.items():
        if not re.fullmatch(r"[1-9][0-9]{0,17}", value):
            raise OrbitError(422, "FIELD_INVALID", "历史分页参数无效")
        number = int(value)
        if key == "pageSize":
            if number > 100:
                raise OrbitError(422, "FIELD_INVALID", "历史页大小必须为1至100")
            size = number
        else:
            if number > 9_007_199_254_740_991:
                raise OrbitError(422, "FIELD_INVALID", "历史版本超出范围")
            before = number
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await ConfigurationStore(credential_cipher()).history(
            session, user.user.user_id, config_id, size, before
        )


async def _save(request: Request, user: CurrentUserModel, config_id: str | None):
    key, expected = _headers(request, updating=config_id is not None)
    # 以流式限额读取，不把敏感请求体放进若依默认防重缓存或操作日志。
    body = bytearray()
    async for part in request.stream():
        body.extend(part)
        if len(body) > 1_048_576:
            raise OrbitError(413, "BODY_TOO_LARGE", "配置请求超过大小限制")
    value = parse_write(bytes(body))
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await ConfigurationStore(credential_cipher(), scanner_registry(request)).save(
            session,
            user.user.user_id,
            key,
            value,
            config_id,
            expected,
            request.state.orbit_request_id,
        )


@router.post("")
async def create_configuration(
    request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    return await _save(request, user, None)


@router.put("/{config_id}")
async def update_configuration(
    config_id: str, request: Request, user: Annotated[CurrentUserModel, CurrentUserDependency()]
):
    return await _save(request, user, config_id)


@router.post("/{config_id}/test")
async def test_configuration_read_only(
    config_id: str,
    request: Request,
    user: Annotated[CurrentUserModel, CurrentUserDependency()],
    probe: Annotated[ModelConnectionProbe, Depends(model_probe)],
):
    import re

    _read_boundary(request)
    revisions = request.headers.getlist("if-match")
    if len(revisions) != 1 or not re.fullmatch(r'"[1-9][0-9]{0,17}"', revisions[0]):
        raise OrbitError(400, "REVISION_REQUIRED", "请提供带引号的配置版本")
    expected = int(revisions[0][1:-1])
    body = bytearray()
    async for part in request.stream():
        if len(body) + len(part) > 16_384:
            raise OrbitError(413, "BODY_TOO_LARGE", "只读测试请求超过大小限制")
        body.extend(part)
    reason = parse_probe_reason(bytes(body))
    registry = scanner_registry(request)
    store = ConfigurationStore(credential_cipher(), registry)
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        context, section, enabled, settings, key = await store.prepare_probe(
            session, user.user.user_id, config_id, expected
        )
    # 外部网络期间不持有数据库行锁或事务；结果写入前再次授权与CAS。
    result = (
        await registry.probe(enabled, settings)
        if section == "MATERIAL_SCANNER"
        else await probe.run(section, enabled, settings, key)
    )
    key = None
    async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
        return await store.finish_probe(
            session, context, config_id, expected, result, reason, request.state.orbit_request_id
        )
