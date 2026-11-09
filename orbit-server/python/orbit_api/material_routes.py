"""素材HTTP边界：只在对象I/O前后短事务授权，不持数据库锁等待文件合并。"""

import asyncio
import re
from typing import Annotated

from common.aspect.pre_auth import CurrentUserDependency
from config.database import DataSourceRegistry
from fastapi import APIRouter, Request
from module_admin.entity.vo.user_vo import CurrentUserModel
from starlette.responses import FileResponse

from orbit_api.configuration import short_text
from orbit_api.configuration_routes import _read_boundary, credential_cipher
from orbit_api.directory_tokens import DirectoryTokens
from orbit_api.errors import OrbitError
from orbit_api.identity_contract import _uuid
from orbit_api.material_contract import (
    PART_SIZE,
    STATES,
    ArchiveWrite,
    AssetWrite,
    BulkDelete,
    CategoryWrite,
    CompleteUpload,
    TagWrite,
    UploadRequest,
    expected_part_size,
    parse_material,
)
from orbit_api.material_library import MaterialLibrary
from orbit_api.material_taxonomy import TAXONOMY_QUERY_FIELDS, parse_taxonomy_filters

User = Annotated[CurrentUserModel, CurrentUserDependency()]


def library():
    return MaterialLibrary(DirectoryTokens(credential_cipher()))


async def bounded_body(request, maximum=65536):
    value = bytearray()
    async for block in request.stream():
        if len(value) + len(block) > maximum:
            raise OrbitError(413, "BODY_TOO_LARGE", "素材请求超过大小限制")
        value.extend(block)
    return bytes(value)


def write_headers(request, *, version=False):
    keys = request.headers.getlist("idempotency-key")
    csrf = request.headers.getlist("x-csrf-token")
    matches = request.headers.getlist("if-match")
    if len(keys) != 1 or not re.fullmatch(r"[ -~]{16,128}", keys[0]):
        raise OrbitError(400, "IDEMPOTENCY_REQUIRED", "请提供16至128位ASCII幂等键")
    if len(csrf) != 1 or not 16 <= len(csrf[0]) <= 255:
        raise OrbitError(403, "CSRF_REQUIRED", "请重新加载有效的会话校验")
    expected = 0
    if version:
        if len(matches) != 1 or not re.fullmatch(r'"[1-9][0-9]{0,15}"', matches[0]):
            raise OrbitError(400, "REVISION_REQUIRED", "请提供带引号的对象版本")
        expected = int(matches[0][1:-1])
        if expected > 9007199254740991:
            raise OrbitError(422, "FIELD_INVALID", "版本超出范围")
    elif matches:
        raise OrbitError(400, "INVALID_STRUCTURE", "此操作不接受If-Match")
    return request.headers.get("authorization", ""), csrf[0], keys[0], expected


def material_filters(request):
    allowed = {
        "q",
        "cursor",
        "page_size",
        "status",
        "category_id",
        "tag_ids",
        "tag_match",
        "kind",
        "sort",
        "direction",
        "operator_user_id",
        "date_from",
        "date_to",
        "channel_id",
        "metric_profile_id",
        "entity_type",
    }
    _read_boundary(request, allowed)
    raw = dict(request.query_params)
    for field in ("date_from", "date_to", "channel_id", "metric_profile_id", "entity_type"):
        if field in raw:
            raise OrbitError(
                503, "MATERIAL_METRICS_UNAVAILABLE", "素材事实筛选尚未接入", "/" + field
            )
    value = {
        "q": short_text(raw.get("q", ""), 100, "/q", required=False),
        "page_size": 50,
        "sort": raw.get("sort", "name"),
        "direction": raw.get("direction", "ASC"),
        "tag_match": raw.get("tag_match", "ALL"),
    }
    if raw.get("page_size", "50") not in {"20", "50", "100", "200"}:
        raise OrbitError(422, "FIELD_INVALID", "分页数量无效", "/page_size")
    value["page_size"] = int(raw.get("page_size", "50"))
    if value["sort"] not in {
        "name",
        "spend",
        "clicks",
        "impressions",
        "roas",
        "conversions",
        "usage",
    }:
        raise OrbitError(422, "FIELD_INVALID", "排序字段无效", "/sort")
    if value["direction"] not in {"ASC", "DESC"} or value["tag_match"] not in {"ALL", "ANY"}:
        raise OrbitError(422, "FIELD_INVALID", "排序或标签关系无效")
    if "status" in raw:
        if raw["status"] not in STATES:
            raise OrbitError(422, "FIELD_INVALID", "素材状态无效", "/status")
        value["status"] = raw["status"]
    if "kind" in raw:
        if raw["kind"] not in {"IMAGE", "VIDEO"}:
            raise OrbitError(422, "FIELD_INVALID", "素材类型无效", "/kind")
        value["kind"] = raw["kind"]
    for field in ("category_id", "operator_user_id"):
        if field in raw:
            value[field] = _uuid(raw[field], "/" + field)
    if "tag_ids" in raw:
        tags = raw["tag_ids"].split(",")
        if len(tags) > 20 or len(set(tags)) != len(tags):
            raise OrbitError(422, "FIELD_INVALID", "最多筛选20个不同标签", "/tag_ids")
        value["tag_ids"] = sorted(_uuid(t, f"/tag_ids/{i}") for i, t in enumerate(tags))
    cursor = raw.get("cursor")
    if cursor is not None and not 1 <= len(cursor) <= 2048:
        raise OrbitError(422, "FIELD_INVALID", "游标长度无效", "/cursor")
    return value, cursor


def create_material_router(objects=None, origin_provider=None):
    """objects只由可信启动配置注入；未配置时读目录可用，文件操作明确503。"""
    router = APIRouter(tags=["ORBIT素材库"])

    def library():
        return MaterialLibrary(
            DirectoryTokens(credential_cipher()), origin_provider=origin_provider
        )

    def storage():
        if objects is None:
            raise OrbitError(503, "MATERIAL_STORAGE_UNAVAILABLE", "尚未配置受控素材对象存储")
        return objects

    @router.get("/api/v1/assets/capabilities")
    async def capabilities(request: Request, user: User):
        _read_boundary(request)
        async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
            return await library().capabilities(
                session, user.user.user_id, request.headers.get("authorization", "")
            )

    @router.get("/api/v1/assets")
    async def list_assets(request: Request, user: User):
        filters, cursor = material_filters(request)
        async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
            return await library().list(session, user.user.user_id, filters, cursor)

    @router.get("/api/v1/assets/security")
    async def security_collection(request: Request, user: User):
        from orbit_api.material_security import read_security, security_ids

        _read_boundary(request, {"asset_ids"})
        identifiers = security_ids(request.query_params.get("asset_ids"))
        async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
            return await read_security(library(), session, user.user.user_id, identifiers)

    @router.get("/api/v1/assets/{asset_id}/security")
    async def asset_security(asset_id: str, request: Request, user: User):
        from orbit_api.material_security import read_security

        _read_boundary(request)
        async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
            result = await read_security(
                library(), session, user.user.user_id, [_uuid(asset_id, "/id")]
            )
            return result["items"][0]

    @router.post("/api/v1/assets/{asset_id}/rescan", status_code=202)
    async def rescan(asset_id: str, request: Request, user: User):
        from orbit_api.material_security import rescan_asset, verify_rescan_source

        _read_boundary(request)
        authorization, csrf, key, expected = write_headers(request, version=True)
        value = parse_material(ArchiveWrite, await bounded_body(request))
        asset_id = _uuid(asset_id, "/id")
        async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
            service = library()
            context, _, replay = await service.begin_write(
                session,
                user.user.user_id,
                authorization,
                csrf,
                key,
                "assets.upload",
                [asset_id, "rescan", expected, value.model_dump()],
            )
            if replay is not None:
                return replay
            snapshot = await service.asset(session, context, asset_id)
            if snapshot["revision"] != expected:
                raise OrbitError(409, "REVISION_CONFLICT", "素材版本已变化，请重新加载")
        await asyncio.to_thread(verify_rescan_source, storage(), context.tenant_id, snapshot)
        async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
            return await rescan_asset(
                library(),
                session,
                user.user.user_id,
                authorization,
                csrf,
                key,
                expected,
                snapshot,
                value,
                request.state.orbit_request_id,
            )

    @router.post("/api/v1/assets/upload-sessions", status_code=201)
    async def create_upload(request: Request, user: User):
        _read_boundary(request)
        storage()
        authorization, csrf, key, _ = write_headers(request)
        value = parse_material(UploadRequest, await bounded_body(request))
        async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
            return await library().create_upload(
                session,
                user.user.user_id,
                authorization,
                csrf,
                key,
                value,
                request.state.orbit_request_id,
            )

    async def snapshot(request, actor, upload_id, csrf, authorization):
        async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
            service = library()
            context, upload, asset = await service.upload_snapshot(
                session, actor, _uuid(upload_id, "/id")
            )
            service.verify_csrf(authorization, actor, context.tenant_id, csrf)
            return context, upload, asset

    @router.put("/api/v1/assets/upload-sessions/{upload_id}/parts/{number}")
    async def upload_part(upload_id: str, number: int, request: Request, user: User):
        _read_boundary(request)
        authorization, csrf, key, _ = write_headers(request)
        context, upload, asset = await snapshot(
            request, user.user.user_id, upload_id, csrf, authorization
        )
        if upload["state"] not in {"INITIATED", "UPLOADING"}:
            raise OrbitError(409, "UPLOAD_STATE_CONFLICT", "上传会话不能再接收分片")
        size = expected_part_size(asset["byte_size"], number)
        content = await bounded_body(request, PART_SIZE)
        etag = await asyncio.to_thread(
            storage().put_part, context.tenant_id, upload_id, number, content, size
        )
        async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
            return await library().record_part(
                session,
                user.user.user_id,
                authorization,
                csrf,
                key,
                upload_id,
                number,
                etag,
                len(content),
                request.state.orbit_request_id,
            )

    @router.post("/api/v1/assets/upload-sessions/{upload_id}/complete", status_code=202)
    async def complete_upload(upload_id: str, request: Request, user: User):
        _read_boundary(request)
        authorization, csrf, key, _ = write_headers(request)
        value = parse_material(CompleteUpload, await bounded_body(request))
        context, upload, asset = await snapshot(
            request, user.user.user_id, upload_id, csrf, authorization
        )
        if upload["state"] != "COMPLETE":
            if value.size != asset["byte_size"] or value.sha256 != asset["sha256"]:
                raise OrbitError(422, "FILE_HASH_INVALID", "上传完成信息与原意图不一致")
            await asyncio.to_thread(
                storage().assemble,
                context.tenant_id,
                upload_id,
                value.parts,
                value.size,
                value.sha256,
                asset["mime"],
            )
        async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
            return await library().complete(
                session,
                user.user.user_id,
                authorization,
                csrf,
                key,
                upload_id,
                value,
                request.state.orbit_request_id,
            )

    @router.post("/api/v1/assets/bulk-delete")
    async def bulk_delete(request: Request, user: User):
        _read_boundary(request)
        authorization, csrf, key, _ = write_headers(request)
        value = parse_material(BulkDelete, await bounded_body(request, 131072))
        async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
            return await library().bulk_delete(
                session,
                user.user.user_id,
                authorization,
                csrf,
                key,
                value,
                request.state.orbit_request_id,
            )

    @router.get("/api/v1/assets/{asset_id}")
    async def get_asset(asset_id: str, request: Request, user: User):
        _read_boundary(request)
        async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
            return await library().get(session, user.user.user_id, _uuid(asset_id, "/id"))

    @router.put("/api/v1/assets/{asset_id}")
    async def edit_asset(asset_id: str, request: Request, user: User):
        _read_boundary(request)
        authorization, csrf, key, expected = write_headers(request, version=True)
        value = parse_material(AssetWrite, await bounded_body(request))
        async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
            return await library().edit(
                session,
                user.user.user_id,
                authorization,
                csrf,
                key,
                _uuid(asset_id, "/id"),
                expected,
                value,
                request.state.orbit_request_id,
            )

    @router.get("/api/v1/assets/{asset_id}/references")
    async def references(asset_id: str, request: Request, user: User):
        _read_boundary(request, {"cursor"})
        async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
            return await library().references(
                session,
                user.user.user_id,
                _uuid(asset_id, "/id"),
                request.query_params.get("cursor", ""),
            )

    @router.get("/api/v1/assets/{asset_id}/preview")
    async def preview(asset_id: str, request: Request, user: User):
        _read_boundary(request)
        async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
            service = library()
            context = await service.context(session, user.user.user_id)
            asset = await service.asset(session, context, _uuid(asset_id, "/id"))
            if asset["state"] != "READY" or not asset["preview_ready"]:
                raise OrbitError(404, "NOT_FOUND", "素材预览尚不可用")
            from orbit_api.material_security import require_clean_scan

            await require_clean_scan(session, context.tenant_id, asset)
        path = storage().preview(context.tenant_id, asset["object_upload_id"])
        return FileResponse(
            path, media_type="image/jpeg", headers={"X-Content-Type-Options": "nosniff"}
        )

    router.include_router(taxonomy_router("TAG", "tags"))
    router.include_router(taxonomy_router("CATEGORY", "categories"))
    return router


def taxonomy_router(kind, path):
    router = APIRouter(prefix="/api/v1/" + path)

    @router.get("")
    async def list_taxonomy(request: Request, user: User):
        _read_boundary(request, TAXONOMY_QUERY_FIELDS)
        filters = parse_taxonomy_filters(dict(request.query_params))
        async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
            return await library().taxonomy_list(
                session, user.user.user_id, kind, request.query_params.get("cursor", ""), filters
            )

    @router.get("/{resource_id}")
    async def get_taxonomy(resource_id: str, request: Request, user: User):
        _read_boundary(request)
        async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
            return await library().taxonomy_get(
                session, user.user.user_id, kind, _uuid(resource_id, "/id")
            )

    async def save(request, user, resource_id=None, archive=False):
        _read_boundary(request)
        authorization, csrf, key, expected = write_headers(request, version=resource_id is not None)
        model = ArchiveWrite if archive else TagWrite if kind == "TAG" else CategoryWrite
        value = parse_material(model, await bounded_body(request))
        async with DataSourceRegistry.session(log_sql=False) as session, session.begin():
            return await library().taxonomy_save(
                session,
                user.user.user_id,
                authorization,
                csrf,
                key,
                kind,
                value,
                request.state.orbit_request_id,
                resource_id,
                expected,
                archive,
            )

    @router.post("", status_code=201)
    async def create(request: Request, user: User):
        return await save(request, user)

    @router.put("/{resource_id}")
    async def update(resource_id: str, request: Request, user: User):
        return await save(request, user, _uuid(resource_id, "/id"))

    @router.post("/{resource_id}/archive")
    async def archive(resource_id: str, request: Request, user: User):
        return await save(request, user, _uuid(resource_id, "/id"), True)

    return router
