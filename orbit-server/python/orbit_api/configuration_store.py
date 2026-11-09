"""系统配置MySQL事务：实时授权、密钥只写、CAS、幂等结果、审计和outbox原子提交。"""

import hashlib
import json
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from orbit_api.authorization import require_configuration_access
from orbit_api.configuration import ConfigurationWrite, metadata, secret_field_names
from orbit_api.credentials import CredentialCipher
from orbit_api.errors import OrbitError

MAX_REVISION = 9_007_199_254_740_991


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode(value):
    return json.loads(value) if isinstance(value, (str, bytes)) else value


def _uuid(value: str) -> str:
    try:
        normalized = str(UUID(value))
        if normalized != value.lower():
            raise ValueError
        return normalized
    except (ValueError, AttributeError):
        raise OrbitError(400, "INVALID_ID", "配置标识格式无效") from None


def _public(row):
    secrets = _decode(row["secrets_json"])
    return {
        "id": row["id"],
        "section": row["section"],
        "name": row["name"],
        "enabled": bool(row["enabled"]),
        "revision": row["revision"],
        "settings": _decode(row["settings_json"]),
        "secrets": {
            key: {
                "configured": bool(secrets.get(key)),
                "hint": "已配置（不回显）" if secrets.get(key) else "未配置",
            }
            for key in secret_field_names(row["section"])
        },
        "verificationStatus": row["verification_status"],
        "verifiedAt": row["verified_at"].isoformat(timespec="milliseconds") + "Z"
        if row["verified_at"]
        else None,
        "updatedAt": row["updated_at"].isoformat(timespec="milliseconds") + "Z",
    }


def _state_hash(row):
    if row is None:
        return None
    # 固定SHA256_STATE_V1业务规范，包含租户与随机密文，排除数据库时间；不摘要Token明文。
    state = {
        "algorithm": "SHA256_STATE_V1",
        "tenantId": row["tenant_id"],
        "id": row["id"],
        "section": row["section"],
        "name": row["name"],
        "enabled": bool(row["enabled"]),
        "revision": row["revision"],
        "verificationStatus": row["verification_status"],
        "settings": _decode(row["settings_json"]),
        "encryptedSecrets": _decode(row["secrets_json"]),
    }
    return hashlib.sha256(_json(state).encode()).hexdigest()


class ConfigurationStore:
    def __init__(self, cipher: CredentialCipher, scanner_registry=None):
        self.cipher = cipher
        from orbit_api.material_scanner_registry import EMPTY_SCANNER_REGISTRY

        self.scanner_registry = (
            scanner_registry if scanner_registry is not None else EMPTY_SCANNER_REGISTRY
        )

    async def list(self, session: AsyncSession, actor: int):
        context = await require_configuration_access(session, actor)
        rows = (
            (
                await session.execute(
                    text("""
            SELECT * FROM orbit_system_configuration WHERE tenant_id=:tenant ORDER BY section,id
        """),
                    {"tenant": context.tenant_id},
                )
            )
            .mappings()
            .all()
        )
        return [_public(row) for row in rows]

    async def get(self, session: AsyncSession, actor: int, config_id: str):
        context = await require_configuration_access(session, actor)
        return _public(await self._row(session, context.tenant_id, _uuid(config_id)))

    async def _row(self, session, tenant, config_id):
        row = (
            (
                await session.execute(
                    text("""
            SELECT * FROM orbit_system_configuration WHERE tenant_id=:tenant AND id=:id FOR UPDATE
        """),
                    {"tenant": tenant, "id": config_id},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise OrbitError(404, "NOT_FOUND", "配置不存在或不可见")
        return row

    async def history(
        self, session: AsyncSession, actor: int, config_id: str, size: int, before: int | None
    ):
        context = await require_configuration_access(session, actor)
        config_id = _uuid(config_id)
        await self._row(session, context.tenant_id, config_id)
        # tenant/config/revision唯一索引反向范围扫描；新增版本不扰乱续页。
        predicate = " AND revision<:before" if before is not None else ""
        rows = (
            (
                await session.execute(
                    text(
                        """
            SELECT id,actor_id,action,revision,before_revision,before_hash,after_hash,
                   hash_algorithm,changed_fields_json,reason,created_at
            FROM orbit_configuration_audit WHERE tenant_id=:tenant AND config_id=:id
        """
                        + predicate
                        + " ORDER BY revision DESC LIMIT :limit"
                    ),
                    {
                        "tenant": context.tenant_id,
                        "id": config_id,
                        "before": before,
                        "limit": size + 1,
                    },
                )
            )
            .mappings()
            .all()
        )
        page = rows[:size]
        return {
            "items": [
                {
                    "id": row["id"],
                    "actorId": row["actor_id"],
                    "action": row["action"],
                    "revision": row["revision"],
                    "beforeRevision": row["before_revision"],
                    "beforeHash": row["before_hash"],
                    "afterHash": row["after_hash"],
                    "hashAlgorithm": row["hash_algorithm"],
                    "changedFields": _decode(row["changed_fields_json"]),
                    "reason": row["reason"],
                    "createdAt": row["created_at"].isoformat(timespec="milliseconds") + "Z",
                }
                for row in page
            ],
            "nextBeforeRevision": page[-1]["revision"] if len(rows) > size else None,
        }

    async def save(
        self,
        session: AsyncSession,
        actor: int,
        key: str,
        request: ConfigurationWrite,
        config_id: str | None = None,
        expected: int = 0,
        request_id: str | None = None,
    ):
        """调用方必须提供事务；外部网络调用不得在该事务中执行。"""
        context = await require_configuration_access(session, actor)
        if request_id is None:
            raise OrbitError(503, "AUDIT_CONTEXT_REQUIRED", "审计请求关联尚不可用")
        request_id = _uuid(request_id)
        tenant = context.tenant_id
        if config_id is not None:
            config_id = _uuid(config_id)
        creating = config_id is None
        if expected < 0 or expected >= MAX_REVISION or (not creating and expected < 1):
            raise OrbitError(400, "REVISION_REQUIRED", "配置版本无效")
        if request.section == "RISK":
            allowed = (
                await session.execute(
                    text("""
                SELECT 1 FROM sys_user_role ur JOIN sys_role r ON r.role_id=ur.role_id
                LEFT JOIN sys_role_menu rm ON rm.role_id=r.role_id
                LEFT JOIN sys_menu m ON m.menu_id=rm.menu_id AND m.status='0'
                WHERE ur.user_id=:actor AND r.status='0' AND r.del_flag='0'
                  AND ((:actor=1 AND r.role_id=1) OR m.perms='system.release.manage')
                LIMIT 1 FOR SHARE
            """),
                    {"actor": actor},
                )
            ).first()
            if allowed is None:
                raise OrbitError(403, "POLICY_FORBIDDEN", "修改执行风控还需要发布管理权限")
        payload = request.model_dump(exclude={"secrets"})
        payload["secrets"] = {
            name: {
                "operation": change.operation,
                "value": change.value.get_secret_value() if change.value is not None else None,
            }
            for name, change in request.secrets.items()
        }
        payload.update(path=config_id or "CREATE", expected=expected)
        sensitive = any(change.operation == "REPLACE" for change in request.secrets.values())
        if sensitive and not self.cipher.ready:
            raise OrbitError(503, "ENCRYPTION_UNAVAILABLE", "服务端尚未配置独立凭据主密钥")
        kid = self.cipher.active_key_id if sensitive else None
        fingerprint = self.cipher.request_digest_internal(_json(payload).encode(), kid)
        params = {"tenant": tenant, "actor": actor, "key": key, "hash": fingerprint, "kid": kid}
        await session.execute(
            text("""
            INSERT INTO orbit_configuration_idempotency
            (tenant_id,actor_id,request_key,payload_hash,payload_key_id)
            VALUES(:tenant,:actor,:key,:hash,:kid) ON DUPLICATE KEY UPDATE request_key=request_key
        """),
            params,
        )
        saved = (
            (
                await session.execute(
                    text("""
            SELECT payload_hash,payload_key_id,response_json FROM orbit_configuration_idempotency
            WHERE tenant_id=:tenant AND actor_id=:actor AND request_key=:key FOR UPDATE
        """),
                    params,
                )
            )
            .mappings()
            .one()
        )
        if sensitive and saved["payload_key_id"] is None:
            raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "幂等键已用于其他请求")
        fingerprint = self.cipher.request_digest_internal(
            _json(payload).encode(), saved["payload_key_id"]
        )
        if fingerprint != saved["payload_hash"]:
            raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "幂等键已用于其他请求")
        if saved["response_json"] is not None:
            response = _decode(saved["response_json"])
            await self._row(session, tenant, response["id"])
            return response
        if request.section == "AI_SUGGESTIONS" and request.enabled:
            # 只在同租户内关联当前启用的模型配置；菜单选择器不能替代服务端引用校验。
            provider = (
                (
                    await session.execute(
                        text("""
                SELECT section,enabled FROM orbit_system_configuration
                WHERE tenant_id=:tenant AND id=:id FOR SHARE
            """),
                        {"tenant": tenant, "id": request.settings["providerConfigId"]},
                    )
                )
                .mappings()
                .first()
            )
            if provider is None:
                raise OrbitError(404, "NOT_FOUND", "AI提供商配置不存在或不可见")
            if not provider["enabled"] or provider["section"] not in {"AI_GPT", "AI_CLAUDE"}:
                raise OrbitError(
                    422,
                    "AI_PROVIDER_UNAVAILABLE",
                    "请选择本租户已启用的GPT或Claude配置",
                    "/settings/providerConfigId",
                )
        if request.section == "MATERIAL_SCANNER" and request.enabled:
            self.scanner_registry.resolve(request.settings["profileId"])
        before = None if creating else await self._row(session, tenant, config_id)
        if before is not None:
            if before["revision"] != expected:
                raise OrbitError(409, "REVISION_CONFLICT", "配置版本已变化，请刷新")
            if before["section"] != request.section:
                raise OrbitError(422, "SECTION_IMMUTABLE", "配置类型不能修改，请新建配置")
        config_id = config_id or str(uuid4())
        fields = next(
            section["fields"] for section in metadata() if section["key"] == request.section
        )
        secrets = dict(_decode(before["secrets_json"])) if before else {}
        changed = []
        for field in fields:
            if field["type"] != "secret":
                continue
            name = field["key"]
            change = request.secrets.get(name)
            if change is not None and change.operation == "REPLACE":
                secrets[name] = self.cipher.encrypt(
                    change.value.get_secret_value(), tenant, config_id, name
                )
                changed.append("secrets." + name + ":REPLACE")
            elif change is not None and change.operation == "CLEAR":
                secrets.pop(name, None)
                changed.append("secrets." + name + ":CLEAR")
            if request.enabled and field["required"] and not secrets.get(name):
                raise OrbitError(
                    422, "SECRET_REQUIRED", "启用配置时必须提供所需凭据", "/secrets/" + name
                )
        previous_settings = _decode(before["settings_json"]) if before else {}
        changed += [
            "settings." + key
            for key, value in request.settings.items()
            if previous_settings.get(key) != value
        ]
        for field in ("name", "enabled"):
            if before is None or before[field] != getattr(request, field):
                changed.append(field)
        now = (await session.execute(text("SELECT UTC_TIMESTAMP(3)"))).scalar_one()
        revision = expected + 1
        values = {
            "id": config_id,
            "tenant": tenant,
            "section": request.section,
            "name": request.name,
            "enabled": request.enabled,
            "revision": revision,
            "settings": _json(request.settings),
            "secrets": _json(secrets),
            "now": now,
            "expected": expected,
        }
        try:
            if creating:
                await session.execute(
                    text("""
                    INSERT INTO orbit_system_configuration
                    (id,tenant_id,section,name,enabled,revision,
                    settings_json,secrets_json,verification_status,created_at,updated_at)
                    VALUES(:id,:tenant,:section,:name,:enabled,:revision,:settings,:secrets,'UNTESTED',:now,:now)
                """),
                    values,
                )
            else:
                updated = await session.execute(
                    text("""
                    UPDATE orbit_system_configuration SET name=:name,enabled=:enabled,
                    revision=:revision,
                    settings_json=:settings,secrets_json=:secrets,verification_status='UNTESTED',verified_at=NULL,
                    updated_at=:now WHERE id=:id AND tenant_id=:tenant AND revision=:expected
                """),
                    values,
                )
                if updated.rowcount != 1:
                    raise OrbitError(409, "REVISION_CONFLICT", "配置版本已变化")
        except IntegrityError:
            if request.section == "MATERIAL_SCANNER":
                raise OrbitError(
                    409, "SCANNER_CONFIGURATION_EXISTS", "每租户只能保存一条素材扫描配置"
                ) from None
            raise OrbitError(409, "CONFIGURATION_CONFLICT", "同类型配置名称已存在") from None
        after = await self._row(session, tenant, config_id)
        await self._append_event(
            session,
            context,
            before,
            after,
            "CREATE" if creating else "UPDATE",
            sorted(changed),
            request.reason,
            request_id,
            now,
        )
        response = _public(after)
        await session.execute(
            text("""
            UPDATE orbit_configuration_idempotency SET response_json=:response
            WHERE tenant_id=:tenant AND actor_id=:actor AND request_key=:key
        """),
            params | {"response": _json(response)},
        )
        return response

    async def _append_event(
        self, session, context, before, after, action, changed, reason, request_id, now
    ):
        """业务状态、审计及待处理事件由同一调用方事务提交，不能单独补写。"""
        event = str(uuid4())
        audit = {
            "event": event,
            "subject": context.subject_id,
            "team": context.team_id,
            "request": request_id,
            "tenant": context.tenant_id,
            "id": after["id"],
            "actor": context.actor_id,
            "action": action,
            "revision": after["revision"],
            "before_revision": before["revision"] if before else 0,
            "before_hash": _state_hash(before),
            "after_hash": _state_hash(after),
            "changed": _json(changed),
            "reason": reason,
            "now": now,
        }
        await session.execute(
            text("""
            INSERT INTO orbit_configuration_audit(id,tenant_id,config_id,actor_id,action,revision,
            before_revision,before_hash,after_hash,hash_algorithm,changed_fields_json,reason,created_at,
            actor_subject_id,actor_team_id,request_id)
            VALUES(:event,:tenant,:id,:actor,:action,:revision,:before_revision,:before_hash,:after_hash,
            'SHA256_STATE_V1',:changed,:reason,:now,:subject,:team,:request)
        """),
            audit,
        )
        await session.execute(
            text("""
            INSERT INTO orbit_configuration_outbox(event_id,tenant_id,config_id,revision,created_at)
            VALUES(:event,:tenant,:id,:revision,:now)
        """),
            audit,
        )

    async def prepare_probe(self, session, actor, config_id, expected):
        context = await require_configuration_access(session, actor)
        row = await self._row(session, context.tenant_id, _uuid(config_id))
        if row["revision"] != expected:
            raise OrbitError(409, "REVISION_CONFLICT", "配置版本已变化，请刷新")
        slot = {
            "AI_GPT": "apiKey",
            "AI_CLAUDE": "apiKey",
            "META_APP": "appSecret",
            "META_BM": "accessToken",
        }.get(row["section"])
        secret = _decode(row["secrets_json"]).get(slot)
        # 仅支持的模型探测才解密；不支持的连接器不接触凭据。
        key = None
        if row["enabled"] and slot and secret:
            key = self.cipher.decrypt_internal(secret, context.tenant_id, row["id"], slot)
        return context, row["section"], bool(row["enabled"]), _decode(row["settings_json"]), key

    async def finish_probe(self, session, context, config_id, expected, result, reason, request_id):
        current = await require_configuration_access(session, context.actor_id)
        if current != context:
            raise OrbitError(403, "PERMISSION_DENIED", "探测期间业务授权已变化，请重新操作")
        before = await self._row(session, current.tenant_id, _uuid(config_id))
        if before["revision"] != expected:
            raise OrbitError(409, "REVISION_CONFLICT", "探测期间配置已变化，请重新测试")
        if before["section"] == "MATERIAL_SCANNER" and result.status == "READ_VERIFIED":
            from orbit_api.material_scanner_registry import ScannerProbeResult

            if (
                not isinstance(result, ScannerProbeResult)
                or result.binding is None
                or not before["enabled"]
            ):
                raise OrbitError(409, "SCANNER_PROFILE_CHANGED", "安全扫描结果缺少当前实例证明")
            if (
                _decode(before["settings_json"]).get("profileId")
                != result.binding.profile.profile_id
            ):
                raise OrbitError(409, "SCANNER_PROFILE_CHANGED", "扫描候选已变化")
            self.scanner_registry.verify(result.binding, source=False)
        if expected >= MAX_REVISION:
            raise OrbitError(409, "REVISION_CONFLICT", "配置版本已达上限")
        now = (await session.execute(text("SELECT UTC_TIMESTAMP(3)"))).scalar_one()
        await session.execute(
            text("""
            UPDATE orbit_system_configuration SET revision=:revision,verification_status=:status,
                verified_at=:now,updated_at=:now
            WHERE tenant_id=:tenant AND id=:id AND revision=:expected
        """),
            {
                "revision": expected + 1,
                "status": result.status,
                "now": now,
                "tenant": current.tenant_id,
                "id": config_id,
                "expected": expected,
            },
        )
        after = await self._row(session, current.tenant_id, config_id)
        await self._append_event(
            session,
            current,
            before,
            after,
            "READ_TEST",
            ["verificationStatus"],
            reason,
            _uuid(request_id),
            now,
        )
        return {
            "configuration": _public(after),
            "result": {"status": result.status, "message": result.message},
        }
