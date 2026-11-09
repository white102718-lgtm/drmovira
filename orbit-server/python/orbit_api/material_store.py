"""素材授权查询和短事务写入；对象I/O必须在事务外完成后复验再登记。"""

import hashlib
import math
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from orbit_api.authorization import require_business_access
from orbit_api.configuration_store import MAX_REVISION, _decode, _uuid
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.material_contract import MIME_KIND, PART_SIZE, expected_part_size
from orbit_api.material_job_policy import actor_auth_version, material_job_scope
from orbit_api.material_security import clean_scan_predicate, require_clean_scan, safe_asset_rows

DEFAULT_CATEGORY = "00000000-0000-4000-8000-000000000001"
ASSET_COLUMNS = """id,owner_user_id,owner_team_id,name,category_id,kind,mime,state,sha256,
 byte_size,object_upload_id,duration_seconds,width_px,height_px,preview_ready,error_code,
 revision,created_at,updated_at,archived_at,physical_cleanup_state"""


async def rows(session, sql, params):
    return (await session.execute(text(sql), params)).mappings().all()


async def one(session, sql, params):
    result = await rows(session, sql, params)
    return result[0] if result else None


def public_asset(row, tags, origin=""):
    return {
        "id": row["id"],
        "name": row["name"],
        "category_id": row["category_id"],
        "tag_ids": sorted(tags),
        "revision": row["revision"],
        "ownership": {"owner_user_id": row["owner_user_id"], "owner_team_id": row["owner_team_id"]},
        "kind": row["kind"],
        "state": row["state"],
        "sha256": row["sha256"],
        "preview_url": f"{origin}/api/v1/assets/{row['id']}/preview"
        if row["preview_ready"] and row.get("_scan_verified", False)
        else None,
        "duration_seconds": format(row["duration_seconds"], "f")
        if row["duration_seconds"] is not None
        else None,
    }


class MaterialStore:
    def __init__(self, tokens, origin_provider=None):
        self.tokens = tokens
        if origin_provider is None:
            from orbit_api.cookie_auth import public_origin

            origin_provider = public_origin
        self.origin_provider = origin_provider

    def public_asset(self, row, tags):
        ready = row["preview_ready"] and row.get("_scan_verified", False)
        return public_asset(row, tags, self.origin_provider() if ready else "")

    async def context(self, session, actor, permission="assets.read"):
        return await require_business_access(session, actor, "assets", permission)

    @staticmethod
    async def scope_version(session, context):
        row = await one(
            session,
            """SELECT revision FROM orbit_directory_clock
            WHERE tenant_id=:tenant""",
            {"tenant": context.tenant_id},
        )
        if row is None:
            raise OrbitError(503, "MATERIAL_NOT_INITIALIZED", "授权目录尚未初始化")
        return row["revision"]

    @staticmethod
    async def visible(session, context, row):
        if context.data_role == "SUPER_ADMIN" or row["owner_user_id"] == context.subject_id:
            return True
        if context.data_role != "TEAM_ADMIN":
            return False
        managed = await one(
            session,
            """SELECT team_id FROM orbit_business_team_manager
            WHERE tenant_id=:tenant AND manager_user_id=:actor AND team_id=:team
              AND enabled=1 FOR SHARE""",
            {"tenant": context.tenant_id, "actor": context.actor_id, "team": row["owner_team_id"]},
        )
        return managed is not None

    async def asset(self, session, context, asset_id, *, lock=False):
        row = await one(
            session,
            f"""SELECT {ASSET_COLUMNS} FROM orbit_material_asset
            WHERE tenant_id=:tenant AND id=:id {"FOR UPDATE" if lock else "FOR SHARE"}""",
            {"tenant": context.tenant_id, "id": _uuid(asset_id)},
        )
        if row is None or not await self.visible(session, context, row):
            raise OrbitError(404, "NOT_FOUND", "素材不存在或不可见")
        return row

    @staticmethod
    async def tags(session, tenant, asset_ids):
        if not asset_ids:
            return {}
        params = {"tenant": tenant}
        placeholders = []
        for i, asset_id in enumerate(asset_ids):
            params[f"id{i}"] = asset_id
            placeholders.append(f":id{i}")
        result = await rows(
            session,
            f"""SELECT asset_id,tag_id FROM orbit_material_asset_tag
           WHERE tenant_id=:tenant AND asset_id IN({",".join(placeholders)})""",
            params,
        )
        mapping = {i: [] for i in asset_ids}
        for item in result:
            mapping[item["asset_id"]].append(item["tag_id"])
        return mapping

    async def get(self, session, actor, asset_id):
        context = await self.context(session, actor)
        row = await self.asset(session, context, asset_id)
        tags = await self.tags(session, context.tenant_id, [row["id"]])
        secured = (await safe_asset_rows(session, context.tenant_id, [row]))[0]
        return self.public_asset(secured, tags[row["id"]])

    async def capabilities(self, session, actor, authorization):
        context = await self.context(session, actor)
        binding = self.tokens.session_binding(authorization, actor, context.tenant_id)
        return {
            "csrf_token": self.tokens.issue("DIRECTORY_CSRF_V1", {"binding": binding}),
            "default_category_id": DEFAULT_CATEGORY,
            "storage_mode": "LOCAL_ISOLATED",
            "max_batch_size": 50,
        }

    def verify_csrf(self, authorization, actor, tenant, csrf):
        try:
            claims = self.tokens.verify("DIRECTORY_CSRF_V1", csrf)
        except OrbitError as error:
            if error.status == 400 and error.code == "TOKEN_INVALID":
                raise OrbitError(403, "CSRF_INVALID", "会话校验无效") from None
            raise
        if claims.get("binding") != self.tokens.session_binding(authorization, actor, tenant):
            raise OrbitError(403, "CSRF_INVALID", "会话校验无效")

    async def begin_write(self, session, actor, authorization, csrf, key, action, value):
        context = await self.context(session, actor, action)
        self.verify_csrf(authorization, actor, context.tenant_id, csrf)
        clock = await one(
            session,
            """SELECT revision FROM orbit_material_clock
            WHERE tenant_id=:tenant FOR UPDATE""",
            {"tenant": context.tenant_id},
        )
        if clock is None:
            raise OrbitError(503, "MATERIAL_NOT_INITIALIZED", "素材目录尚未初始化")
        if clock["revision"] >= MAX_REVISION:
            raise OrbitError(409, "REVISION_EXHAUSTED", "素材目录版本已达上限")
        digest = hashlib.sha256(canonical([action, value]).encode()).hexdigest()
        previous = await one(
            session,
            """SELECT payload_hash,response_json
            FROM orbit_material_idempotency WHERE tenant_id=:tenant AND actor_id=:actor
              AND request_key=:key""",
            {"tenant": context.tenant_id, "actor": actor, "key": key},
        )
        if previous and previous["payload_hash"] != digest:
            raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "相同幂等键对应其他操作")
        replay = _decode(previous["response_json"]) if previous else None
        if (
            replay
            and isinstance(replay, dict)
            and (replay.get("state") == "READY" or replay.get("part_size") == 0)
        ):
            resource = replay.get("asset_id") if "asset_id" in replay else replay.get("id")
            current = await self.asset(session, context, resource)
            await require_clean_scan(session, context.tenant_id, current)
        return context, digest, replay

    @staticmethod
    async def changed(session, context, action, resource_id, revision, request_id, change=None):
        params = {
            "event": str(uuid4()),
            "tenant": context.tenant_id,
            "actor": context.actor_id,
            "action": action,
            "id": resource_id,
            "revision": revision,
            "request": request_id,
            "change": canonical(change or {}),
        }
        await session.execute(
            text("""INSERT INTO orbit_material_audit
           (id,tenant_id,actor_id,action,resource_id,revision,request_id,change_json)
           VALUES(:event,:tenant,:actor,:action,:id,:revision,:request,:change)"""),
            params,
        )
        await session.execute(
            text("""INSERT INTO orbit_material_outbox
           (event_id,tenant_id,resource_id,revision) VALUES(:event,:tenant,:id,:revision)"""),
            params,
        )

    @staticmethod
    async def finish(session, context, key, digest, response):
        params = {
            "tenant": context.tenant_id,
            "actor": context.actor_id,
            "key": key,
            "digest": digest,
            "response": canonical(response),
        }
        await session.execute(
            text("""INSERT INTO orbit_material_idempotency
           (tenant_id,actor_id,request_key,payload_hash,response_json)
           VALUES(:tenant,:actor,:key,:digest,:response)"""),
            params,
        )
        await session.execute(
            text("""UPDATE orbit_material_clock SET revision=revision+1
           WHERE tenant_id=:tenant"""),
            params,
        )
        return response

    @staticmethod
    async def validate_metadata(session, context, value, old_tags=()):
        params = {"tenant": context.tenant_id, "id": value.category_id}
        category = await one(
            session,
            """SELECT state FROM orbit_material_taxonomy
            WHERE tenant_id=:tenant AND id=:id AND kind='CATEGORY' FOR SHARE""",
            params,
        )
        if category is None or category["state"] != "ENABLED":
            raise OrbitError(422, "CATEGORY_DISABLED", "请选择有效分类", "/category_id")
        selected = {}
        if value.tag_ids:
            params = {"tenant": context.tenant_id} | {
                f"tag{i}": tag_id for i, tag_id in enumerate(value.tag_ids)
            }
            placeholders = ",".join(f":tag{i}" for i in range(len(value.tag_ids)))
            selected = {
                row["id"]: row["state"]
                for row in await rows(
                    session,
                    f"""SELECT id,state FROM orbit_material_taxonomy WHERE tenant_id=:tenant
                AND kind='TAG' AND id IN({placeholders}) ORDER BY id FOR SHARE""",
                    params,
                )
            }
        for tag_id in value.tag_ids:
            if tag_id not in selected or selected[tag_id] != "ENABLED" and tag_id not in old_tags:
                raise OrbitError(422, "TAG_DISABLED", "不可新增停用标签", "/tag_ids")

    async def replace_tags(self, session, tenant, asset_id, tag_ids):
        params = {"tenant": tenant, "asset": asset_id}
        await session.execute(
            text("""DELETE FROM orbit_material_asset_tag
            WHERE tenant_id=:tenant AND asset_id=:asset"""),
            params,
        )
        if tag_ids:
            await session.execute(
                text("""INSERT INTO orbit_material_asset_tag
                (tenant_id,asset_id,tag_id) VALUES(:tenant,:asset,:tag)"""),
                [{**params, "tag": i} for i in tag_ids],
            )

    async def create_upload(self, session, actor, authorization, csrf, key, value, request_id):
        context, digest, replay = await self.begin_write(
            session, actor, authorization, csrf, key, "assets.upload", value.model_dump()
        )
        if replay is not None:
            return replay
        await self.validate_metadata(session, context, value.metadata)
        # 仅同拥有者READY素材可复用；不同拥有者永远创建独立业务对象。
        duplicate = await one(
            session,
            f"""SELECT {ASSET_COLUMNS} FROM orbit_material_asset a
            WHERE tenant_id=:tenant AND owner_user_id=:owner AND sha256=:hash AND state='READY'
              AND byte_size=:size AND mime=:mime AND physical_cleanup_state='LIVE'
              AND {clean_scan_predicate()} ORDER BY id LIMIT 1 FOR SHARE""",
            {
                "tenant": context.tenant_id,
                "owner": context.subject_id,
                "hash": value.sha256,
                "size": value.size,
                "mime": value.mime,
            },
        )
        asset_id, upload_id = str(uuid4()), str(uuid4())
        if duplicate:
            asset_id = duplicate["id"]
        expires = datetime.now(UTC) + timedelta(hours=24)
        params = {
            "tenant": context.tenant_id,
            "id": asset_id,
            "upload": upload_id,
            "owner": context.subject_id,
            "team": context.team_id,
            "name": value.metadata.name,
            "category": value.metadata.category_id,
            "kind": MIME_KIND[value.mime],
            "mime": value.mime,
            "hash": value.sha256,
            "size": value.size,
            "expires": expires.replace(tzinfo=None),
        }
        if not duplicate:
            await session.execute(
                text("""INSERT INTO orbit_material_asset
              (tenant_id,id,owner_user_id,owner_team_id,name,category_id,kind,mime,state,sha256,
               byte_size,object_upload_id) VALUES(:tenant,:id,:owner,:team,:name,:category,:kind,
               :mime,'INITIATED',:hash,:size,:upload)"""),
                params,
            )
            await self.replace_tags(session, context.tenant_id, asset_id, value.metadata.tag_ids)
        # 去重时仍返回合同规定的非空parts；客户端complete会直接返回已有READY，不写对象。
        await session.execute(
            text("""INSERT INTO orbit_material_upload
           (tenant_id,id,asset_id,owner_user_id,expires_at,state)
           VALUES(:tenant,:upload,:id,:owner,:expires,:state)"""),
            {**params, "state": "COMPLETE" if duplicate else "INITIATED"},
        )
        response = {
            "id": upload_id,
            "asset_id": asset_id,
            "expires_at": expires.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "part_size": 0 if duplicate else PART_SIZE,
            "parts": [
                {
                    "part_number": i,
                    "url": self.origin_provider()
                    + f"/api/v1/assets/upload-sessions/{upload_id}/parts/{i}",
                }
                for i in range(1, math.ceil(value.size / PART_SIZE) + 1)
            ],
        }
        change = {
            "reuse": bool(duplicate),
            "state": {
                "before": "READY" if duplicate else None,
                "after": "READY" if duplicate else "INITIATED",
            },
        }
        if not duplicate:
            change["metadata"] = {"before": None, "after": value.metadata.model_dump()}
        await self.changed(
            session,
            context,
            "UPLOAD_REUSED" if duplicate else "UPLOAD_CREATED",
            asset_id,
            duplicate["revision"] if duplicate else 1,
            request_id,
            change,
        )
        return await self.finish(session, context, key, digest, response)

    async def upload_snapshot(self, session, actor, upload_id):
        context = await self.context(session, actor, "assets.upload")
        upload = await one(
            session,
            """SELECT id,asset_id,owner_user_id,state,expires_at
            FROM orbit_material_upload WHERE tenant_id=:tenant AND id=:id FOR SHARE""",
            {"tenant": context.tenant_id, "id": _uuid(upload_id)},
        )
        if upload is None or upload["owner_user_id"] != context.subject_id:
            raise OrbitError(404, "NOT_FOUND", "上传会话不存在或不可见")
        if upload["expires_at"] <= datetime.now(UTC).replace(tzinfo=None):
            raise OrbitError(409, "UPLOAD_EXPIRED", "上传会话已过期")
        asset = await self.asset(session, context, upload["asset_id"])
        return context, upload, asset

    async def record_part(
        self, session, actor, authorization, csrf, key, upload_id, number, etag, size, request_id
    ):
        payload = [upload_id, number, etag, size]
        context, digest, replay = await self.begin_write(
            session, actor, authorization, csrf, key, "assets.upload", payload
        )
        if replay is not None:
            return replay
        _, upload, asset = await self.upload_snapshot(session, actor, upload_id)
        if upload["state"] not in {"INITIATED", "UPLOADING"}:
            raise OrbitError(409, "UPLOAD_STATE_CONFLICT", "当前上传状态不能接收分片")
        if expected_part_size(asset["byte_size"], number) != size:
            raise OrbitError(422, "PART_SIZE_INVALID", "分片尺寸不符")
        params = {
            "tenant": context.tenant_id,
            "upload": upload_id,
            "number": number,
            "etag": etag,
            "size": size,
            "asset": asset["id"],
        }
        previous = await one(
            session,
            """SELECT etag,byte_size FROM orbit_material_upload_part
            WHERE tenant_id=:tenant AND upload_id=:upload AND part_number=:number""",
            params,
        )
        if previous and (previous["etag"] != etag or previous["byte_size"] != size):
            raise OrbitError(409, "PART_CONFLICT", "相同分片已有不同内容")
        if not previous:
            await session.execute(
                text("""INSERT INTO orbit_material_upload_part
               (tenant_id,upload_id,part_number,byte_size,etag)
               VALUES(:tenant,:upload,:number,:size,:etag)"""),
                params,
            )
        await session.execute(
            text("""UPDATE orbit_material_upload SET state='UPLOADING'
            WHERE tenant_id=:tenant AND id=:upload"""),
            params,
        )
        await session.execute(
            text("""UPDATE orbit_material_asset SET state='UPLOADING',
            revision=revision+1,updated_at=UTC_TIMESTAMP(3)
            WHERE tenant_id=:tenant AND id=:asset AND revision<9007199254740991"""),
            params,
        )
        await self.changed(
            session,
            context,
            "UPLOAD_PART",
            asset["id"],
            asset["revision"] + 1,
            request_id,
            {"part_number": number, "state": {"before": asset["state"], "after": "UPLOADING"}},
        )
        return await self.finish(
            session, context, key, digest, {"part_number": number, "etag": etag}
        )

    async def complete(
        self, session, actor, authorization, csrf, key, upload_id, value, request_id
    ):
        context, digest, replay = await self.begin_write(
            session,
            actor,
            authorization,
            csrf,
            key,
            "assets.upload",
            [upload_id, "complete", value.model_dump()],
        )
        if replay is not None:
            return replay
        _, upload, asset = await self.upload_snapshot(session, actor, upload_id)
        if asset["state"] == "READY" and upload["state"] == "COMPLETE":
            await require_clean_scan(session, context.tenant_id, asset)
            response = self.public_asset(
                dict(asset) | {"_scan_verified": True},
                (await self.tags(session, context.tenant_id, [asset["id"]]))[asset["id"]],
            )
            return await self.finish(session, context, key, digest, response)
        if upload["state"] not in {"INITIATED", "UPLOADING"}:
            raise OrbitError(409, "UPLOAD_STATE_CONFLICT", "上传已经完成或取消")
        if value.size != asset["byte_size"] or value.sha256 != asset["sha256"]:
            raise OrbitError(422, "FILE_HASH_INVALID", "完成请求与原上传意图不一致")
        recorded = await rows(
            session,
            """SELECT part_number,etag FROM orbit_material_upload_part
           WHERE tenant_id=:tenant AND upload_id=:upload ORDER BY part_number FOR SHARE""",
            {"tenant": context.tenant_id, "upload": upload_id},
        )
        if [dict(p) for p in recorded] != [p.model_dump() for p in value.parts]:
            raise OrbitError(422, "PARTS_INVALID", "尚有分片未确认或摘要不符")
        params = {"tenant": context.tenant_id, "upload": upload_id, "asset": asset["id"]}
        await session.execute(
            text("""UPDATE orbit_material_upload SET state='COMPLETE'
            WHERE tenant_id=:tenant AND id=:upload"""),
            params,
        )
        await session.execute(
            text("""UPDATE orbit_material_asset SET state='SCANNING',
            revision=revision+1,updated_at=UTC_TIMESTAMP(3)
            WHERE tenant_id=:tenant AND id=:asset"""),
            params,
        )
        await session.execute(
            text("""INSERT INTO orbit_material_job
            (tenant_id,asset_id,actor_id,actor_auth_version,scope_digest,state)
            VALUES(:tenant,:asset,:actor,:auth,:scope,'PENDING')"""),
            {
                **params,
                "actor": actor,
                "auth": await actor_auth_version(session, actor),
                "scope": material_job_scope(context, asset),
            },
        )
        row = {**asset, "state": "SCANNING", "revision": asset["revision"] + 1}
        tags = await self.tags(session, context.tenant_id, [asset["id"]])
        response = self.public_asset(row, tags[asset["id"]])
        await self.changed(
            session,
            context,
            "UPLOAD_COMPLETED",
            asset["id"],
            row["revision"],
            request_id,
            {"state": {"before": asset["state"], "after": "SCANNING"}},
        )
        return await self.finish(session, context, key, digest, response)
