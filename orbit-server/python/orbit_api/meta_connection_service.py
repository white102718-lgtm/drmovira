"""Meta连接事务；外部授权交换在两个短事务之间，state先消耗再联网。"""

import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import text

from orbit_api.account_access import event
from orbit_api.authorization import require_system_access
from orbit_api.cookie_identity import current_cookie_identity
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.meta_connection_contract import return_path


def validate_state_row(row, *, tenant, actor, browser, app_id, now):
    """一次性状态、发起主体与浏览器会话必须同时一致。"""
    if (
        row is None
        or row["status"] != "PENDING"
        or row["expires_at"] <= now
        or row["tenant_id"] != tenant
        or row["actor_id"] != actor
        or row["browser_session_id"] != browser
        or row["app_id"] != app_id
    ):
        raise OrbitError(400, "META_STATE_INVALID", "Meta授权已过期、已使用或不属于当前会话")


async def lock_account_clock(session, tenant):
    """与账户Worker一致：账户时钟先于连接/授权状态；撤销不因归属投影延迟被阻断。"""
    version = (
        await session.execute(
            text("SELECT revision FROM orbit_account_clock WHERE tenant_id=:tenant FOR UPDATE"),
            {"tenant": tenant},
        )
    ).scalar_one_or_none()
    if version is None:
        raise OrbitError(503, "ACCOUNT_INITIALIZATION_REQUIRED", "账户业务迁移尚未完成")
    if version >= 9007199254740991:
        raise OrbitError(409, "REVISION_EXHAUSTED", "账户目录版本已达上限")


async def lock_principal(session, app_id, principal_id):
    """发布与平台撤销先锁已验证主体，再锁租户时钟；Worker不申请主体锁。"""
    values = {"app": app_id, "principal": principal_id}
    await session.execute(
        text(
            "INSERT INTO orbit_meta_principal_lock(app_id,principal_id) VALUES(:app,:principal) "
            "ON DUPLICATE KEY UPDATE principal_id=principal_id"
        ),
        values,
    )
    return (
        await session.execute(
            text(
                "SELECT last_revoked_at FROM orbit_meta_principal_lock "
                "WHERE app_id=:app AND principal_id=:principal FOR UPDATE"
            ),
            values,
        )
    ).scalar_one()


def require_publication_epoch(revoked_at, started_at):
    if revoked_at is not None and revoked_at >= started_at:
        raise OrbitError(409, "META_AUTHORIZATION_REVOKED", "验证期间授权已被撤销，请重新发起")


def validate_exchange_row(row, **expected):
    if row is None or row["status"] != "EXCHANGING":
        raise OrbitError(409, "META_STATE_INVALID", "授权交换状态已失效")
    validate_state_row(dict(row) | {"status": "PENDING"}, **expected)


async def access(session, actor):
    return await require_system_access(
        session, actor, 31081, "system.integrations.manage", super_admin=False
    )


def browser_identity(actor):
    identity = current_cookie_identity()
    if identity is None or identity.actor_id != actor:
        raise OrbitError(401, "SESSION_REQUIRED", "请使用当前浏览器登录后连接Meta")
    return identity


def utc_string(value):
    return value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z") if value else None


class MetaConnectionService:
    def __init__(self, sessions, cipher, app, transport):
        self.sessions, self.cipher, self.app, self.transport = sessions, cipher, app, transport

    async def start(self, actor, target, key, request_id, connection_id=None):
        identity = browser_identity(actor)
        target = return_path(target)
        if not isinstance(key, str) or not 1 <= len(key) <= 128 or not key.isascii():
            raise OrbitError(400, "IDEMPOTENCY_KEY_REQUIRED", "需要有效幂等键")
        payload = hashlib.sha256(
            canonical(
                {
                    "return_to": target,
                    "connection_id": connection_id,
                    "app": self.app.app_id,
                    "application_id": self.app.configuration_id,
                    "application_revision": self.app.configuration_revision,
                }
            ).encode()
        ).hexdigest()
        async with self.sessions() as session, session.begin():
            current = await access(session, actor)
            if self.app is not None:
                from orbit_api.meta_application_registry import verify_application

                await verify_application(session, self.cipher, current.tenant_id, self.app)
            # 账户时钟串行同租户写入，避免将权限检查持有的浏览器共享锁升级造成死锁。
            await lock_account_clock(session, current.tenant_id)
            old = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM orbit_meta_authorization_session WHERE "
                            "tenant_id=:tenant AND browser_session_id=:browser AND "
                            "request_key=:key FOR UPDATE"
                        ),
                        {"tenant": current.tenant_id, "browser": identity.session_id, "key": key},
                    )
                )
                .mappings()
                .first()
            )
            now = (await session.execute(text("SELECT UTC_TIMESTAMP(3)"))).scalar_one()
            if old:
                if old["payload_hash"] != payload:
                    raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "幂等键已用于其他授权请求")
                validate_state_row(
                    old,
                    tenant=current.tenant_id,
                    actor=actor,
                    browser=identity.session_id,
                    app_id=self.app.app_id,
                    now=now,
                )
                state = self.cipher.decrypt_internal(
                    old["state_envelope"], current.tenant_id, old["id"], "meta_state"
                )
                return {
                    "authorize_url": self.app.authorize_url(state),
                    "expires_at": utc_string(old["expires_at"]),
                }
            revision = None
            if connection_id:
                old_connection = await self.connection(session, current, connection_id, lock=True)
                if old_connection["kind"] != "LOGIN" or old_connection["app_id"] != self.app.app_id:
                    raise OrbitError(
                        409, "META_BM_RECONNECT_REQUIRED", "BM连接请从系统配置重新验证接入"
                    )
                revision = old_connection["revision"]
            state = secrets.token_urlsafe(32)
            identifier = str(uuid4())
            expires = now + timedelta(minutes=10)
            await session.execute(
                text("""INSERT INTO orbit_meta_authorization_session
                (id,tenant_id,actor_id,browser_session_id,state_digest,state_envelope,request_key,payload_hash,return_to,connection_id,connection_revision,app_id,app_configuration_id,app_configuration_revision,status,expires_at,created_at)
                VALUES(:id,:tenant,:actor,:browser,:digest,:envelope,:key,:hash,:target,:connection,:revision,:app,:app_config,:app_revision,'PENDING',:expires,:now)"""),
                {
                    "id": identifier,
                    "tenant": current.tenant_id,
                    "actor": actor,
                    "browser": identity.session_id,
                    "digest": hashlib.sha256(state.encode()).digest(),
                    "envelope": self.cipher.encrypt(
                        state, current.tenant_id, identifier, "meta_state"
                    ),
                    "key": key,
                    "hash": payload,
                    "target": target,
                    "connection": connection_id,
                    "revision": revision,
                    "app": self.app.app_id,
                    "app_config": self.app.configuration_id,
                    "app_revision": self.app.configuration_revision,
                    "expires": expires,
                    "now": now,
                },
            )
            await event(
                session,
                current,
                "META_CONNECTION",
                identifier,
                1,
                "META_AUTHORIZATION_STARTED",
                request_id,
                {},
            )
            return {
                "authorize_url": self.app.authorize_url(state),
                "expires_at": utc_string(expires),
            }

    async def bind_application(self, session, tenant, identifier):
        await session.execute(
            text(
                "UPDATE orbit_meta_connection SET app_configuration_id=:config, "
                "app_configuration_revision=:revision WHERE tenant_id=:tenant AND id=:id"
            ),
            {
                "config": self.app.configuration_id,
                "revision": self.app.configuration_revision,
                "tenant": tenant,
                "id": identifier,
            },
        )

    async def connection(self, session, current, identifier, *, lock=False):
        row = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM orbit_meta_connection WHERE tenant_id=:tenant AND id=:id "
                        + ("FOR UPDATE" if lock else "FOR SHARE")
                    ),
                    {"tenant": current.tenant_id, "id": identifier},
                )
            )
            .mappings()
            .first()
        )
        if row is None or (
            current.data_role != "SUPER_ADMIN" and row["actor_id"] != current.actor_id
        ):
            raise OrbitError(404, "NOT_FOUND", "Meta连接不存在或不可见")
        return dict(row)

    async def callback(self, actor, state, code, request_id, *, cancelled=False):
        identity = browser_identity(actor)
        if not isinstance(state, str) or not 20 <= len(state) <= 256:
            raise OrbitError(400, "META_STATE_INVALID", "Meta授权状态无效")
        digest = hashlib.sha256(state.encode()).digest()
        async with self.sessions() as session, session.begin():
            current = await access(session, actor)
            from orbit_api.meta_application_registry import verify_application

            await verify_application(session, self.cipher, current.tenant_id, self.app)
            await lock_account_clock(session, current.tenant_id)
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM orbit_meta_authorization_session WHERE "
                            "state_digest=:digest FOR UPDATE"
                        ),
                        {"digest": digest},
                    )
                )
                .mappings()
                .first()
            )
            now = (await session.execute(text("SELECT UTC_TIMESTAMP(3)"))).scalar_one()
            validate_state_row(
                row,
                tenant=current.tenant_id,
                actor=actor,
                browser=identity.session_id,
                app_id=self.app.app_id,
                now=now,
            )
            row = dict(row)
            await session.execute(
                text(
                    "UPDATE orbit_meta_authorization_session SET status=:status,"
                    "state_envelope=IF(:status='CANCELLED','',state_envelope) WHERE id=:id"
                ),
                {"id": row["id"], "status": "CANCELLED" if cancelled else "EXCHANGING"},
            )
            await event(
                session,
                current,
                "META_CONNECTION",
                row["id"],
                2,
                "META_AUTHORIZATION_CANCELLED" if cancelled else "META_AUTHORIZATION_CONSUMED",
                request_id,
                {},
            )
        if cancelled:
            return row["return_to"], "cancelled"
        try:
            token, grant = await self.transport.exchange(code)
            async with self.sessions() as session, session.begin():
                current = await access(session, actor)
                await verify_application(session, self.cipher, current.tenant_id, self.app)
                if (
                    current.tenant_id != row["tenant_id"]
                    or browser_identity(actor).session_id != row["browser_session_id"]
                ):
                    raise OrbitError(403, "META_STATE_INVALID", "授权期间登录身份已变化")
                revoked = await lock_principal(
                    session, self.app.principal_namespace, grant.principal_id
                )
                require_publication_epoch(revoked, row["created_at"])
                await lock_account_clock(session, current.tenant_id)
                latest_state = (
                    (
                        await session.execute(
                            text(
                                "SELECT * FROM orbit_meta_authorization_session WHERE id=:id F"
                                "OR UPDATE"
                            ),
                            {"id": row["id"]},
                        )
                    )
                    .mappings()
                    .first()
                )
                committed_at = (await session.execute(text("SELECT UTC_TIMESTAMP(3)"))).scalar_one()
                validate_exchange_row(
                    latest_state,
                    tenant=current.tenant_id,
                    actor=actor,
                    browser=identity.session_id,
                    app_id=self.app.app_id,
                    now=committed_at,
                )
                if any(
                    deadline is None or deadline.replace(tzinfo=None) <= committed_at
                    for deadline in (grant.expires_at, grant.data_access_expires_at)
                ):
                    raise OrbitError(
                        409, "META_AUTHORIZATION_EXPIRED", "返回授权已过期，请重新发起"
                    )
                old = None
                if row["connection_id"]:
                    old = await self.connection(session, current, row["connection_id"], lock=True)
                    if (
                        old["revision"] != row["connection_revision"]
                        or old["kind"] != "LOGIN"
                        or old["app_id"] != self.app.app_id
                        or old["principal_id"] != grant.principal_id
                    ):
                        raise OrbitError(409, "META_SOURCE_CHANGED", "重新授权主体或来源版本已变化")
                else:
                    old = (
                        (
                            await session.execute(
                                text(
                                    "SELECT * FROM orbit_meta_connection WHERE "
                                    "tenant_id=:tenant AND actor_id=:actor AND app_id=:app AND "
                                    "kind='LOGIN' AND principal_id=:principal FOR UPDATE"
                                ),
                                {
                                    "tenant": current.tenant_id,
                                    "actor": actor,
                                    "app": self.app.app_id,
                                    "principal": grant.principal_id,
                                },
                            )
                        )
                        .mappings()
                        .first()
                    )
                    if old:
                        raise OrbitError(
                            409, "META_ALREADY_CONNECTED", "此Meta身份已连接，请使用重新授权入口"
                        )
                identifier = old["id"] if old else str(uuid4())
                revision = old["revision"] + 1 if old else 1
                values = {
                    "tenant": current.tenant_id,
                    "id": identifier,
                    "actor": actor,
                    "principal": grant.principal_id,
                    "app": self.app.app_id,
                    "revision": revision,
                    "envelope": self.cipher.encrypt(
                        token, current.tenant_id, identifier, "meta_token"
                    ),
                    "scopes": json.dumps(grant.scopes),
                    "expires": grant.expires_at.replace(tzinfo=None) if grant.expires_at else None,
                    "data_expires": grant.data_access_expires_at.replace(tzinfo=None)
                    if grant.data_access_expires_at
                    else None,
                }
                if old:
                    await session.execute(
                        text(
                            "UPDATE orbit_meta_connection SET revision=:revision,status='ACTIVE"
                            "',token_envelope=:envelope,scopes_json=:scopes,expires_at=:expires"
                            ",data_access_expires_at=:data_expires,updated_at=UTC_TIMESTAMP(3) "
                            "WHERE tenant_id=:tenant AND id=:id"
                        ),
                        values,
                    )
                    await session.execute(
                        text(
                            "UPDATE orbit_meta_account_source SET "
                            "connection_revision=:revision,revision=revision+1 WHERE "
                            "tenant_id=:tenant AND connection_id=:id"
                        ),
                        values,
                    )
                else:
                    await session.execute(
                        text(
                            "INSERT INTO orbit_meta_connection (tenant_id,id,actor_id,kind,prin"
                            "cipal_id,app_id,status,revision,token_envelope,scopes_json,expires"
                            "_at,data_access_expires_at,created_at,updated_at) VALUES(:tenant,:"
                            "id,:actor,'LOGIN',:principal,:app,'ACTIVE',:revision,:envelope,:sc"
                            "opes,:expires,:data_expires,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))"
                        ),
                        values,
                    )
                await self.bind_application(session, current.tenant_id, identifier)
                await session.execute(
                    text(
                        "UPDATE orbit_meta_authorization_session SET "
                        "status='COMPLETED',state_envelope='' WHERE id=:id AND "
                        "status='EXCHANGING'"
                    ),
                    {"id": row["id"]},
                )
                await event(
                    session,
                    current,
                    "META_CONNECTION",
                    identifier,
                    revision,
                    "META_CONNECTED",
                    request_id,
                    {"kind": "LOGIN"},
                )
            return row["return_to"], "connected"
        except Exception:
            # state已消耗，不重放授权码。仅更新状态，不保存外部异常原文。
            async with self.sessions() as session, session.begin():
                await lock_account_clock(session, row["tenant_id"])
                changed = await session.execute(
                    text(
                        "UPDATE orbit_meta_authorization_session SET "
                        "status='FAILED',state_envelope='' WHERE id=:id AND tenant_id=:tenant "
                        "AND status='EXCHANGING'"
                    ),
                    {"id": row["id"], "tenant": row["tenant_id"]},
                )
                if changed.rowcount:
                    audit = SimpleNamespace(
                        tenant_id=row["tenant_id"], actor_id=row["actor_id"], subject_id=""
                    )
                    await event(
                        session,
                        audit,
                        "META_CONNECTION",
                        row["id"],
                        3,
                        "META_AUTHORIZATION_FAILED",
                        request_id,
                        {"error_code": "META_AUTHORIZATION_FAILED"},
                    )
            raise OrbitError(
                400, "META_AUTHORIZATION_FAILED", "Meta授权未完成，请重新发起并确认读取权限"
            ) from None

    async def list_connections(self, actor):
        async with self.sessions() as session, session.begin():
            current = await access(session, actor)
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT id,kind,status,revision,principal_id,expires_at,data_access"
                            "_expires_at,updated_at FROM orbit_meta_connection WHERE "
                            "tenant_id=:tenant "
                            + ("" if current.data_role == "SUPER_ADMIN" else "AND actor_id=:actor ")
                            + "ORDER BY created_at DESC,id LIMIT 201"
                        ),
                        {"tenant": current.tenant_id, "actor": actor},
                    )
                )
                .mappings()
                .all()
            )
            if len(rows) > 200:
                raise OrbitError(
                    503,
                    "META_CONNECTION_LIST_LIMIT",
                    "Meta连接超过当前列表容量，请联系管理员分批处理",
                )
            now = datetime.now(UTC).replace(tzinfo=None)
            return {
                "items": [
                    dict(r)
                    | {
                        "status": "REAUTH_REQUIRED"
                        if r["status"] == "ACTIVE"
                        and any(
                            d is not None and d <= now
                            for d in (r["expires_at"], r["data_access_expires_at"])
                        )
                        else r["status"],
                        "expires_at": utc_string(r["expires_at"]),
                        "data_access_expires_at": utc_string(r["data_access_expires_at"]),
                        "updated_at": utc_string(r["updated_at"]),
                    }
                    for r in rows
                ]
            }

    async def disconnect(self, actor, identifier, revision, reason, key, request_id):
        if (
            type(revision) is not int
            or revision < 1
            or not isinstance(reason, str)
            or not 1 <= len(reason.strip()) <= 500
        ):
            raise OrbitError(422, "FIELD_INVALID", "请提供连接版本及断开原因")
        digest = hashlib.sha256(
            canonical({"id": identifier, "revision": revision, "reason": reason}).encode()
        ).hexdigest()
        async with self.sessions() as session, session.begin():
            current = await access(session, actor)
            await lock_account_clock(session, current.tenant_id)
            row = await self.connection(session, current, identifier, lock=True)
            prior = (
                (
                    await session.execute(
                        text(
                            "SELECT input_hash,result_json FROM orbit_meta_request_receipt "
                            "WHERE tenant_id=:tenant AND actor_id=:actor AND request_key=:key "
                            "FOR UPDATE"
                        ),
                        {"tenant": current.tenant_id, "actor": actor, "key": key},
                    )
                )
                .mappings()
                .first()
            )
            if prior:
                if prior["input_hash"] != digest:
                    raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "此幂等键已用于其他操作")
                return (
                    json.loads(prior["result_json"])
                    if isinstance(prior["result_json"], str)
                    else prior["result_json"]
                )
            if row["revision"] != revision:
                raise OrbitError(409, "META_SOURCE_CHANGED", "Meta连接已更新，请刷新")
            await session.execute(
                text(
                    "UPDATE orbit_meta_connection SET status='DISCONNECTED',token_envelope=NULL"
                    ",revision=revision+1,updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=:tenant "
                    "AND id=:id"
                ),
                {"tenant": current.tenant_id, "id": identifier},
            )
            result = {"id": identifier, "status": "DISCONNECTED", "revision": revision + 1}
            await event(
                session,
                current,
                "META_CONNECTION",
                identifier,
                revision + 1,
                "META_DISCONNECTED",
                request_id,
                {"reason": reason},
            )
            await session.execute(
                text(
                    "INSERT INTO orbit_meta_request_receipt "
                    "(tenant_id,actor_id,request_key,input_hash,result_json,created_at) "
                    "VALUES(:tenant,:actor,:key,:hash,:result,UTC_TIMESTAMP(3))"
                ),
                {
                    "tenant": current.tenant_id,
                    "actor": actor,
                    "key": key,
                    "hash": digest,
                    "result": canonical(result),
                },
            )
            return result

    async def candidates(self, actor, identifier):
        """只返回服务端完整枚举候选，每页复核权限且网络不占用数据库事务。"""
        from orbit_api.meta_account_sources import load_connection
        from orbit_api.meta_read_adapter import MetaReadAdapter
        from orbit_api.meta_read_contract import MetaReadFailure

        async def freeze(expected=None):
            async with self.sessions() as session, session.begin():
                current = await access(session, actor)
                row = await self.connection(session, current, identifier)
                self.require_live(row)
                if expected is not None and row["revision"] != expected:
                    raise OrbitError(409, "META_SOURCE_CHANGED", "枚举期间连接已更新，请重试")
                source = await load_connection(
                    session,
                    self.cipher,
                    current.tenant_id,
                    identifier,
                    row["revision"],
                    self.app.graph_version,
                )
                return current, row, source

        current, row, source = await freeze()
        frozen_revision = row["revision"]
        adapter = MetaReadAdapter(source.configuration)
        items = {}
        try:
            for edge in ("me",) if source.kind == "LOGIN" else ("owned", "client"):
                checkpoint = None
                for _ in range(50):
                    await freeze(frozen_revision)
                    page = await adapter.accounts_page(
                        edge=edge, business_id=source.business_id, checkpoint=checkpoint
                    )
                    for record in page.items:
                        items[record["account_id"]] = {
                            "external_id": record["account_id"],
                            "name": record.get("name"),
                            "currency": record.get("currency"),
                            "timezone": record.get("timezone_name"),
                        }
                    if page.complete:
                        break
                    checkpoint = page.checkpoint
                else:
                    raise OrbitError(
                        503, "META_ACCOUNT_LIST_INCOMPLETE", "可访问账户枚举尚未完成，请联系管理员"
                    )
            await freeze(frozen_revision)
        except MetaReadFailure as error:
            if error.code == "META_AUTH_FAILED":
                async with self.sessions() as session, session.begin():
                    current = await access(session, actor)
                    await lock_account_clock(session, current.tenant_id)
                    latest = await self.connection(session, current, identifier, lock=True)
                    if latest["revision"] == frozen_revision:
                        await session.execute(
                            text(
                                "UPDATE orbit_meta_connection SET status='REAUTH_REQUIRED',tok"
                                "en_envelope=NULL,revision=revision+1,updated_at=UTC_TIMESTAMP"
                                "(3) WHERE tenant_id=:tenant AND id=:id"
                            ),
                            {"tenant": current.tenant_id, "id": identifier},
                        )
                        await event(
                            session,
                            current,
                            "META_CONNECTION",
                            identifier,
                            frozen_revision + 1,
                            "META_AUTHORIZATION_EXPIRED",
                            str(uuid4()),
                            {},
                        )
            raise OrbitError(
                503 if error.retryable else 409,
                error.code,
                "Meta账户读取未完成，请检查连接状态或稍后重试",
            ) from None
        return {
            "items": list(items.values()),
            "next_cursor": None,
            "connection_revision": frozen_revision,
        }

    @staticmethod
    def require_live(row):
        now = datetime.now(UTC).replace(tzinfo=None)
        if (
            row["status"] != "ACTIVE"
            or not row["token_envelope"]
            or any(
                d is not None and d <= now
                for d in (row["expires_at"], row["data_access_expires_at"])
            )
        ):
            raise OrbitError(409, "META_REAUTH_REQUIRED", "此连接需要重新授权")

    async def connect_bm(self, actor, configuration_id, configuration_revision, key, request_id):
        """管理员BM凭据仍由原配置管理；实际枚举成功才创建读取连接。"""
        from orbit_api.authorization import require_configuration_access
        from orbit_api.configuration_store import _decode
        from orbit_api.meta_read_adapter import MetaReadAdapter
        from orbit_api.meta_read_contract import MetaReadConfiguration

        async def load(session, *, publishing=False):
            current = await require_configuration_access(session, actor)
            from orbit_api.meta_application_registry import verify_application

            await verify_application(session, self.cipher, current.tenant_id, self.app)
            if publishing:
                revoked = await lock_principal(
                    session, self.app.principal_namespace, grant.principal_id
                )
                require_publication_epoch(revoked, validation_started_at)
                await lock_account_clock(session, current.tenant_id)
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM orbit_system_configuration WHERE tenant_id=:tenant "
                            "AND id=:id AND section='META_BM' AND enabled=1 AND verification_s"
                            "tatus='READ_VERIFIED' AND revision=:revision FOR SHARE"
                        ),
                        {
                            "tenant": current.tenant_id,
                            "id": configuration_id,
                            "revision": configuration_revision,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise OrbitError(
                    409, "META_BM_CONFIGURATION_CHANGED", "BM配置不存在、已停用或版本已变化"
                )
            return current, row

        async with self.sessions() as session, session.begin():
            current, config = await load(session)
            validation_started_at = (
                await session.execute(text("SELECT UTC_TIMESTAMP(6)"))
            ).scalar_one()
            encrypted = _decode(config["secrets_json"]).get("accessToken")
            if not encrypted:
                raise OrbitError(
                    503, "META_BM_CREDENTIAL_REQUIRED", "请先在BM配置中保存系统用户凭据"
                )
            token = self.cipher.decrypt_internal(
                encrypted, current.tenant_id, configuration_id, "accessToken"
            )
            settings = _decode(config["settings_json"])
        try:
            grant = await self.transport.validate(token, system_user=True)
            await self.transport.verify_system_user(
                token, settings.get("businessId"), grant.principal_id
            )
        except Exception:
            async with self.sessions() as session, session.begin():
                await lock_account_clock(session, current.tenant_id)
                await event(
                    session,
                    current,
                    "META_CONNECTION",
                    configuration_id,
                    configuration_revision,
                    "META_BM_VERIFICATION_FAILED",
                    request_id,
                    {"error_code": "META_BM_VERIFICATION_FAILED"},
                )
            raise OrbitError(
                400, "META_BM_VERIFICATION_FAILED", "BM凭据主体尚未通过系统用户验证"
            ) from None
        if "business_management" not in grant.scopes:
            raise OrbitError(
                403, "META_BM_PERMISSION_REQUIRED", "枚举BM资源需要business_management权限"
            )
        adapter = MetaReadAdapter(
            MetaReadConfiguration(
                configuration_id, configuration_revision, self.app.graph_version, token
            )
        )
        count = 0
        for edge in ("owned", "client"):
            checkpoint = None
            for _ in range(50):
                async with self.sessions() as session, session.begin():
                    await load(session)
                page = await adapter.accounts_page(
                    edge=edge, business_id=settings.get("businessId"), checkpoint=checkpoint
                )
                count += len(page.items)
                if page.complete:
                    break
                checkpoint = page.checkpoint
            else:
                raise OrbitError(503, "META_ACCOUNT_LIST_INCOMPLETE", "BM可访问账户枚举尚未完成")
        if count == 0:
            raise OrbitError(
                422, "META_NO_ACCESSIBLE_ACCOUNTS", "此系统用户在指定BM下暂无可访问广告账户"
            )
        digest = hashlib.sha256(
            canonical(
                {"configuration_id": configuration_id, "revision": configuration_revision}
            ).encode()
        ).hexdigest()
        async with self.sessions() as session, session.begin():
            current, _ = await load(session, publishing=True)
            prior = (
                (
                    await session.execute(
                        text(
                            "SELECT input_hash,result_json FROM orbit_meta_request_receipt WHE"
                            "RE tenant_id=:tenant AND actor_id=:actor AND request_key=:key FOR"
                            " UPDATE"
                        ),
                        {"tenant": current.tenant_id, "actor": actor, "key": key},
                    )
                )
                .mappings()
                .first()
            )
            if prior:
                if prior["input_hash"] != digest:
                    raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "幂等键已用于其他接入")
                return _decode(prior["result_json"])
            old = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM orbit_meta_connection WHERE tenant_id=:tenant AND a"
                            "ctor_id=:actor AND app_id=:app AND kind='BM' AND principal_id=:pr"
                            "incipal FOR UPDATE"
                        ),
                        {
                            "tenant": current.tenant_id,
                            "actor": actor,
                            "app": self.app.app_id,
                            "principal": grant.principal_id,
                        },
                    )
                )
                .mappings()
                .first()
            )
            identifier = old["id"] if old else str(uuid4())
            revision = old["revision"] + 1 if old else 1
            values = {
                "tenant": current.tenant_id,
                "id": identifier,
                "actor": actor,
                "principal": grant.principal_id,
                "app": self.app.app_id,
                "revision": revision,
                "envelope": self.cipher.encrypt(token, current.tenant_id, identifier, "meta_token"),
                "scopes": json.dumps(grant.scopes),
                "expires": grant.expires_at.replace(tzinfo=None) if grant.expires_at else None,
                "data_expires": grant.data_access_expires_at.replace(tzinfo=None)
                if grant.data_access_expires_at
                else None,
                "configuration": configuration_id,
                "configuration_revision": configuration_revision,
            }
            if old:
                await session.execute(
                    text(
                        "UPDATE orbit_meta_connection SET status='ACTIVE',revision=:revision,t"
                        "oken_envelope=:envelope,scopes_json=:scopes,expires_at=:expires,data_"
                        "access_expires_at=:data_expires,configuration_id=:configuration,confi"
                        "guration_revision=:configuration_revision,updated_at=UTC_TIMESTAMP(3)"
                        " WHERE tenant_id=:tenant AND id=:id"
                    ),
                    values,
                )
                await session.execute(
                    text(
                        "UPDATE orbit_meta_account_source SET connection_revision=:revision,re"
                        "vision=revision+1 WHERE tenant_id=:tenant AND connection_id=:id"
                    ),
                    values,
                )
            else:
                await session.execute(
                    text(
                        "INSERT INTO orbit_meta_connection (tenant_id,id,actor_id,kind,princip"
                        "al_id,app_id,status,revision,token_envelope,scopes_json,expires_at,da"
                        "ta_access_expires_at,configuration_id,configuration_revision,created_"
                        "at,updated_at) VALUES(:tenant,:id,:actor,'BM',:principal,:app,'ACTIVE"
                        "',:revision,:envelope,:scopes,:expires,:data_expires,:configuration,:"
                        "configuration_revision,UTC_TIMESTAMP(3),UTC_TIMESTAMP(3))"
                    ),
                    values,
                )
            await self.bind_application(session, current.tenant_id, identifier)
            result = {
                "id": identifier,
                "revision": revision,
                "status": "ACTIVE",
                "kind": "BM",
                "accessible_account_count": count,
            }
            await event(
                session,
                current,
                "META_CONNECTION",
                identifier,
                revision,
                "META_BM_CONNECTED",
                request_id,
                {
                    "configuration_id": configuration_id,
                    "configuration_revision": configuration_revision,
                },
            )
            await session.execute(
                text(
                    "INSERT INTO orbit_meta_request_receipt (tenant_id,actor_id,request_key,in"
                    "put_hash,result_json,created_at) VALUES(:tenant,:actor,:key,:hash,:result"
                    ",UTC_TIMESTAMP(3))"
                ),
                {
                    "tenant": current.tenant_id,
                    "actor": actor,
                    "key": key,
                    "hash": digest,
                    "result": canonical(result),
                },
            )
            return result

    async def provider_callback(self, signed, kind):
        """Meta签名取消授权立即废止凭据；删除请求单独排队，不伪造已清除历史。"""
        from orbit_api.authorization import BusinessContext
        from orbit_api.meta_connection_contract import signed_request

        if kind not in {"DELETE", "DEAUTHORIZE"}:
            raise ValueError("回调类型无效")
        try:
            data = signed_request(signed, self.app.app_secret, datetime.now(UTC))
        except ValueError:
            raise OrbitError(400, "META_SIGNATURE_INVALID", "Meta回调签名无效或过期") from None
        digest = hashlib.sha256(
            (self.app.principal_namespace + ":" + kind + ":" + signed).encode()
        ).hexdigest()
        source_filter = (
            " AND app_configuration_id=:config"
            if self.app.configuration_id
            else " AND app_configuration_id IS NULL"
        )
        source_params = {
            "app": self.app.app_id,
            "principal": data["user_id"],
            "config": self.app.configuration_id,
        }
        async with self.sessions() as session, session.begin():
            await lock_principal(session, self.app.principal_namespace, data["user_id"])
            prior = (
                (
                    await session.execute(
                        text(
                            "SELECT id,status FROM orbit_meta_callback_receipt WHERE request_h"
                            "ash=:hash FOR UPDATE"
                        ),
                        {"hash": digest},
                    )
                )
                .mappings()
                .first()
            )
            if prior:
                return dict(prior)
            # 发布同主体必须先取上面的互斥锁，因此此租户集合在回调事务内稳定。
            tenants = (
                (
                    await session.execute(
                        text(
                            "SELECT DISTINCT tenant_id FROM orbit_meta_connection "
                            "WHERE app_id=:app AND principal_id=:principal"
                            + source_filter
                            + " ORDER BY tenant_id"
                        ),
                        source_params,
                    )
                )
                .scalars()
                .all()
            )
            for tenant in tenants:
                await lock_account_clock(session, tenant)
            await session.execute(
                text(
                    "UPDATE orbit_meta_principal_lock SET last_revoked_at=UTC_TIMESTAMP(6) "
                    "WHERE app_id=:app AND principal_id=:principal"
                ),
                {"app": self.app.principal_namespace, "principal": data["user_id"]},
            )
            rows = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM orbit_meta_connection WHERE app_id=:app AND princip"
                            "al_id=:principal" + source_filter + " ORDER BY tenant_id,id FOR UPDATE"
                        ),
                        source_params,
                    )
                )
                .mappings()
                .all()
            )
            for row in rows:
                await session.execute(
                    text(
                        "UPDATE orbit_meta_connection SET status='DISCONNECTED',token_envelope"
                        "=NULL,revision=revision+1,updated_at=UTC_TIMESTAMP(3) WHERE tenant_id"
                        "=:tenant AND id=:id"
                    ),
                    {"tenant": row["tenant_id"], "id": row["id"]},
                )
                current = BusinessContext(row["actor_id"], row["tenant_id"], "SUPER_ADMIN", "", "")
                await event(
                    session,
                    current,
                    "META_CONNECTION",
                    row["id"],
                    row["revision"] + 1,
                    "META_" + kind,
                    str(uuid4()),
                    {},
                )
            identifier = str(uuid4())
            status = "PENDING" if kind == "DELETE" else "COMPLETED"
            await session.execute(
                text(
                    "INSERT INTO orbit_meta_callback_receipt (id,app_id,principal_id,kind,requ"
                    "est_hash,status,created_at) VALUES(:id,:app,:principal,:kind,:hash,:statu"
                    "s,UTC_TIMESTAMP(3))"
                ),
                {
                    "id": identifier,
                    "app": self.app.app_id,
                    "principal": data["user_id"],
                    "kind": kind,
                    "hash": digest,
                    "status": status,
                },
            )
            return {"id": identifier, "status": status}
