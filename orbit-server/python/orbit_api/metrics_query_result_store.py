"""049结果构建的受控生命周期；不发行事实、不接公共路由、不作平台写入。

所有数据库事务均由本服务持有的同一连接执行。临时表不是可回滚DDL，
清理失败的连接必须失效，不能把未知连接状态送回池。原API只有完整200，
未完成的构建不得以Task或202表示成功。
"""

import asyncio
import hashlib
import json
import re
import secrets
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from types import MappingProxyType
from uuid import uuid4
from weakref import WeakKeyDictionary, ref
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from orbit_api.directory_tokens import DirectoryTokens, canonical
from orbit_api.errors import OrbitError
from orbit_api.metrics_aggregation import MetricGroup
from orbit_api.metrics_contract import (
    MetricRow,
    MetricTotal,
    parse_metric_query,
    validate_account_local_today,
)
from orbit_api.metrics_query_result import (
    RESULT_ALGORITHM_VERSION,
    DisplayContribution,
    MetricResultRow,
    MetricResultTotal,
    ResultGroupKey,
    metrics_page,
    validate_outbound,
)
from orbit_api.metrics_query_result_contract import (
    EXPECTED_STREAM_VERSION,
    ExpectedStreamVerifier,
    ExpectedUnitManifest,
    QuerySourceIdentity,
    require_expected_provider,
    strict_hash,
    strict_integer,
    strict_uuid,
    unverified,
)
from orbit_api.metrics_query_store import (
    MetricsQueryStore,
    literal_contains,
    numerator,
    rows,
    transaction,
)
from orbit_api.metrics_scope_access import authorize_metric_scope

LEASE_SECONDS = 60
CHILD_TABLES = (
    "orbit_metric_query_sorted_row",
    "orbit_metric_query_total",
    "orbit_metric_query_expected_account",
)
STAGE_NAMES = (
    "unit",
    "member",
    "cell",
    "fact",
    "dimension",
    "contribution",
    "matched",
    "filtered",
    "display",
    "unit_sum",
    "group_count",
    "cell_field_proof",
    "total_unit",
    "total_count",
    "result",
    "ordered",
    "publish_row",
    "accountproof",
    "total",
)
VALUE_NAMES = ("spend", "impressions", "clicks", "registrations", "purchases", "purchase_value")
OWNED_LOCK_WAIT_SECONDS = 1


async def _owned_settings(connection):
    if connection.invalidated or connection.closed:
        raise OrbitError(503, "METRICS_STAGE_CLEANUP_UNVERIFIED", "原指标构建连接已失效")
    value = (
        (
            await connection.execute(
                text(
                    "SELECT CONNECTION_ID() AS connection_id,"
                    "@@SESSION.innodb_lock_wait_timeout AS lock_wait_timeout"
                )
            )
        )
        .mappings()
        .one()
    )
    identifier, timeout = value["connection_id"], value["lock_wait_timeout"]
    strict_integer(identifier, minimum=1)
    strict_integer(timeout, minimum=1, maximum=1073741824)
    return identifier, timeout


async def _restore_owned_settings(connection, identifier, original):
    # 已失效时绝不执行SQL：下一次execute可能连接到另一个server CID。
    if connection.invalidated:
        return
    if connection.closed or identifier is None or original is None:
        raise OrbitError(503, "METRICS_STAGE_CLEANUP_UNVERIFIED", "原连接设置未完整核验")
    if connection.in_transaction():
        await connection.rollback()
    current, _ = await _owned_settings(connection)
    if current != identifier:
        raise OrbitError(503, "METRICS_STAGE_CLEANUP_UNVERIFIED", "原指标连接身份已变化")
    await connection.execute(
        text("SET SESSION innodb_lock_wait_timeout=:seconds"), {"seconds": original}
    )
    restored_id, restored = await _owned_settings(connection)
    if restored_id != identifier or restored != original:
        raise OrbitError(503, "METRICS_STAGE_CLEANUP_UNVERIFIED", "原指标连接设置未能还原")
    await connection.commit()


@asynccontextmanager
async def _owned_result_connection(engine):
    """仅本次独占物理会话设置一秒锁等待；正常退出同CID还原，不触全局。"""
    connection = await engine.connect()
    identifier = original = None
    try:
        async with asyncio.timeout(5):
            identifier, original = await _owned_settings(connection)
            await connection.execute(
                text("SET SESSION innodb_lock_wait_timeout=:seconds"),
                {"seconds": OWNED_LOCK_WAIT_SECONDS},
            )
            current, configured = await _owned_settings(connection)
            if current != identifier or configured != OWNED_LOCK_WAIT_SECONDS:
                raise OrbitError(503, "METRICS_STAGE_CLEANUP_UNVERIFIED", "指标连接设置未能核验")
            await connection.commit()
        try:
            yield connection
        except asyncio.CancelledError:
            # 取消也可能恰好发生在两条SQL之间，驱动不一定自动invalidate。
            # 此owned连接永不因一次成功rollback而重新成为可用池会话。
            try:
                if not connection.invalidated and not connection.closed:
                    connection.sync_connection.detach()
            except BaseException:
                pass
            try:
                async with asyncio.timeout(1):
                    await connection.invalidate()
            except BaseException:
                pass
            raise
    finally:
        failed = sys.exc_info()[0] is not None
        try:
            async with asyncio.timeout(5):
                await _restore_owned_settings(connection, identifier, original)
                await connection.close()
        except BaseException:
            try:
                if not connection.invalidated and not connection.closed:
                    connection.sync_connection.detach()
            except BaseException:
                pass
            try:
                async with asyncio.timeout(1):
                    await connection.invalidate()
                    await connection.close()
            except BaseException:
                pass
            if not failed:
                raise OrbitError(
                    503, "METRICS_STAGE_CLEANUP_UNVERIFIED", "原指标连接清理尚未确认"
                ) from None


@dataclass(frozen=True)
class ResultBuildBudget:
    """内部显式资源预算，不改变原请求合法上限；超出整包失败并保留原key。"""

    max_input_rows: int
    max_output_rows: int
    max_input_bytes: int
    max_output_bytes: int
    max_seconds: int

    def __post_init__(self):
        for value in vars(self).values():
            strict_integer(value, minimum=1)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def now_utc(clock):
    value = clock()
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        unverified()
    return value.astimezone(UTC).replace(tzinfo=None)


def busy():
    raise OrbitError(409, "METRICS_QUERY_BUSY", "指标查询仍在完整构建，请保留原意图后重读")


def stale_claim():
    raise OrbitError(409, "METRICS_BUILD_CLAIM_LOST", "指标查询构建代次已变化")


class _BuildTicket:
    __slots__ = ("__weakref__",)


@dataclass(frozen=True, repr=False)
class _Claim:
    connection: object
    actor: int
    tenant: str
    query_id: str
    generation: int
    token_hash: str
    manifest: ExpectedUnitManifest


class _StageTicket:
    __slots__ = ("__weakref__",)


class _TemporaryStage:
    """仅由已取得独占连接的服务创建；名为服务端UUID，不接受请求标识符。"""

    def __init__(self, connection):
        self.connection = connection
        nonce = uuid4().hex
        self.names = MappingProxyType({kind: f"it_mqr_{nonce}_{kind}" for kind in STAGE_NAMES})
        self.created = []
        self.closed = False
        self.input_rows = 0
        self.input_bytes = 0
        self.connection_id = None
        self.cleanup_verified = False
        self.cleanup_state = "PENDING"

    def _usable(self):
        return not self.connection.invalidated and not self.connection.closed

    async def _original_connection(self):
        if not self._usable():
            raise OrbitError(503, "METRICS_STAGE_CLEANUP_UNVERIFIED", "指标构建连接已失效")
        result = await self.connection.execute(text("SELECT CONNECTION_ID()"))
        identifier = result.scalar_one()
        strict_integer(identifier, minimum=1)
        if self.connection_id is None:
            self.connection_id = identifier
        elif identifier != self.connection_id:
            raise OrbitError(503, "METRICS_STAGE_CLEANUP_UNVERIFIED", "指标构建连接身份已变化")

    async def create(self, kind, definition, parameters=None):
        if self.closed or kind not in self.names or kind in self.created:
            raise ValueError("临时结果阶段或表名不合法")
        await self._original_connection()
        # 在发送DDL前登记，响应丢失仍会尝试清理确切名称。
        self.created.append(kind)
        statement = text(f"CREATE TEMPORARY TABLE {self.names[kind]} {definition}")
        if parameters is None:
            await self.connection.execute(statement)
        else:
            await self.connection.execute(statement, parameters)
        return self.names[kind]

    async def _drop(self):
        self.cleanup_state = "FAILED"
        try:
            async with asyncio.timeout(5):
                if not self._usable():
                    raise OrbitError(503, "METRICS_STAGE_CLEANUP_UNVERIFIED", "原构建连接已失效")
                if self.connection.in_transaction():
                    await self.connection.rollback()
                await self._original_connection()
                for kind in reversed(self.created):
                    if not self._usable():
                        raise OrbitError(
                            503, "METRICS_STAGE_CLEANUP_UNVERIFIED", "原构建连接已失效"
                        )
                    await self.connection.execute(
                        text(f"DROP TEMPORARY TABLE IF EXISTS {self.names[kind]}")
                    )
                if self.connection.in_transaction():
                    await self.connection.rollback()
                await self._original_connection()
                if self.connection.in_transaction():
                    await self.connection.rollback()
                self.cleanup_verified = True
                self.cleanup_state = "DROPPED"
        except BaseException:
            # detach不发SQL：不确定的原物理连接即使关闭超时，也绝不回到共享池。
            try:
                if self._usable():
                    self.connection.sync_connection.detach()
            except BaseException:
                pass
            try:
                async with asyncio.timeout(1):
                    await self.connection.invalidate()
            except BaseException:
                pass
            raise OrbitError(
                503,
                "METRICS_STAGE_CLEANUP_UNVERIFIED",
                "指标构建临时状态未能完整确认清理，不能继续使用该构建连接",
            ) from None
        finally:
            self.closed = True

    async def close(self):
        if self.closed:
            return
        cleanup = asyncio.create_task(self._drop())
        cancelled = False
        # 重复取消也不能让持有临时表的连接提前归池；独立_drop有自己的5秒上限。
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                cancelled = True
            except BaseException:
                if cancelled:
                    raise asyncio.CancelledError from None
                raise
        if cancelled:
            raise asyncio.CancelledError
        cleanup.result()


class MetricsQueryResultStore:
    """内部构建协调器。所有方法先要求两个真实Provider，缺失时零SQL503。"""

    def __init__(
        self, read_store=None, expected_provider=None, *, clock=None, budget=None, tokens=None
    ):
        self.read = read_store or MetricsQueryStore()
        self.expected_provider = expected_provider
        self.clock = clock or (lambda: datetime.now(UTC))
        self._claims = WeakKeyDictionary()
        self._stages = WeakKeyDictionary()
        self.budget = budget
        self.tokens = tokens

    def _providers(self):
        self.read._provider()
        expected = require_expected_provider(self.expected_provider)
        if expected.kind != self.read.source_provider.kind:
            unverified()
        return expected

    async def _describe(self, session, context):
        return await self.read.describe_context(session, context)

    async def _manifest(self, session, actor, context):
        provider = self._providers()
        metadata = await self._describe(session, context)
        scope = await authorize_metric_scope(session, actor, metadata["scope_snapshot_id"])
        source = QuerySourceIdentity(
            metadata["tenant_id"],
            metadata["source_publication_id"],
            metadata["source_generation"],
            metadata["profile_id"],
            metadata["profile_version"],
            metadata["profile_hash"],
            metadata["authority_kind"],
        )
        manifest = await provider.prepare_manifest(session, scope, metadata["query"], source)
        self._check_manifest(metadata, manifest)
        # 首次准备也重验，避免Provider中途切来源/授权或把任意同形对象作True回执。
        checked = await provider.revalidate_manifest(session, scope, metadata["query"], manifest)
        if type(checked) is not ExpectedUnitManifest or checked != manifest:
            unverified()
        await self._describe(session, context)
        return metadata, manifest

    @staticmethod
    def _check_manifest(metadata, manifest):
        if type(manifest) is not ExpectedUnitManifest:
            unverified()
        source = manifest.source
        expected = {
            "actor_id": metadata["actor_id"],
            "subject_id": metadata["subject_id"],
            "auth_version": metadata["auth_version"],
            "auth_fingerprint": metadata["auth_fingerprint"],
            "query_hash": metadata["query_hash"],
            "dataset": metadata["query"]["dataset"],
            "scope_snapshot_id": metadata["scope_snapshot_id"],
            "scope_hash": metadata["scope_hash"],
            "scope_count": metadata["scope_count"],
        }
        if any(
            type(getattr(manifest, key)) is not type(value) or getattr(manifest, key) != value
            for key, value in expected.items()
        ):
            unverified()
        if (manifest.date_from.isoformat(), manifest.date_to.isoformat()) != (
            metadata["query"]["date_from"],
            metadata["query"]["date_to"],
        ):
            unverified()
        if (
            source.tenant_id,
            source.publication_id,
            source.generation,
            source.profile_id,
            source.profile_version,
            source.profile_hash,
            source.authority_kind,
        ) != (
            metadata["tenant_id"],
            metadata["source_publication_id"],
            metadata["source_generation"],
            metadata["profile_id"],
            metadata["profile_version"],
            metadata["profile_hash"],
            metadata["authority_kind"],
        ):
            unverified()

    @staticmethod
    def _header_manifest(header, manifest):
        if header.get("algorithm_version") != RESULT_ALGORITHM_VERSION:
            unverified()
        strict_integer(header.get("expected_account_count"))
        expected = {
            "expected_manifest_version": EXPECTED_STREAM_VERSION,
            "expected_cell_count": manifest.unit_count,
            "expected_unit_hash": manifest.unit_hash,
            "expected_membership_count": manifest.membership_count,
            "expected_membership_hash": manifest.membership_hash,
        }
        if any(
            type(header.get(key)) is not type(value) or header[key] != value
            for key, value in expected.items()
        ):
            unverified()

    async def _expected_account_count(self, session, actor, metadata, manifest):
        scope = await authorize_metric_scope(session, actor, metadata["scope_snapshot_id"])
        verifier = ExpectedStreamVerifier(manifest)
        count, previous = 0, None
        async for batch in self.expected_provider.iter_unit_batches(
            session, scope, metadata["query"], manifest
        ):
            verifier.add(batch)
            for unit in batch:
                if unit.account_id != previous:
                    count += 1
                    previous = unit.account_id
        verifier.finish()
        strict_integer(count)
        return count

    async def prepare(self, session, actor, query, key, request_id, authorization=""):
        """T1登记完整意图与独立预期根；调用方显式commit后才能进入build。"""
        self._providers()
        transaction(session)
        strict_integer(actor, minimum=1)
        strict_uuid(request_id)
        if (
            type(key) is not str
            or not 1 <= len(key) <= 128
            or not key.isascii()
            or any(ord(char) < 32 or ord(char) > 126 for char in key)
        ):
            raise OrbitError(400, "IDEMPOTENCY_KEY_INVALID", "幂等键格式不符合原合同")
        parsed = parse_metric_query(canonical(query).encode())
        request_hash = digest(query)  # 第一次await前冻结原请求，不改成解析后或恢复时的新意图。
        # 在查key前仍须当前真实monitor权限，不借同key跳过撤权。
        current = await authorize_metric_scope(session, actor, None)
        key_hash = digest(key)
        existing = await rows(
            session,
            "SELECT r.* FROM orbit_metric_query_request r WHERE r.tenant_id=:tenant "
            "AND r.actor_id=:actor AND r.key_hash=:key_hash FOR SHARE",
            {"tenant": current.current.tenant_id, "actor": actor, "key_hash": key_hash},
        )
        if existing:
            if len(existing) != 1 or existing[0]["request_hash"] != request_hash:
                raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "同一幂等键不能变更指标查询意图")
            context = await self.read.resume_persisted_query(
                session, actor, existing[0]["query_id"]
            )
            metadata, manifest = await self._manifest(session, actor, context)
            header = await self._header(session, metadata["tenant_id"], existing[0]["query_id"])
            self._header_manifest(header, manifest)
            return MappingProxyType(
                {"query_id": header["id"], "state": header["state"], "replayed": True}
            )
        if parsed["cursor"] is not None:
            if not isinstance(self.tokens, DirectoryTokens):
                unverified()
            claims = self.tokens.verify("METRICS_QUERY_CURSOR_V1", parsed["cursor"])
            query_id = strict_uuid(claims.get("q"))
            # 先完整执行当前授权与游标绑定复核，不能只解码q后登记意图。
            await self.page(session, actor, query_id, parsed, authorization)
            await session.execute(
                text("""INSERT INTO orbit_metric_query_request(
             tenant_id,actor_id,key_hash,request_hash,query_id,after_ordinal,page_size,request_id,created_at)
             VALUES(:tenant,:actor,:key_hash,:request_hash,:id,:after,:size,:request_id,:now)"""),
                {
                    "tenant": current.current.tenant_id,
                    "actor": actor,
                    "key_hash": key_hash,
                    "request_hash": request_hash,
                    "id": query_id,
                    "after": claims["n"],
                    "size": parsed["page_size"],
                    "request_id": request_id,
                    "now": now_utc(self.clock),
                },
            )
            return MappingProxyType({"query_id": query_id, "state": "READY", "replayed": False})
        context = await self.read.select_source_anchor(session, actor, parsed)
        metadata, manifest = await self._manifest(session, actor, context)
        account_count = await self._expected_account_count(session, actor, metadata, manifest)
        query_id = str(uuid4())
        token_hash = digest(secrets.token_hex(32))
        stamp = now_utc(self.clock)
        values = dict(metadata) | {
            "id": query_id,
            "query_json": canonical(dict(metadata["query"])),
            "algorithm": RESULT_ALGORITHM_VERSION,
            "token_hash": token_hash,
            "now": stamp,
            "lease": stamp,
            "unit_count": manifest.unit_count,
            "account_count": account_count,
            "unit_hash": manifest.unit_hash,
            "member_count": manifest.membership_count,
            "member_hash": manifest.membership_hash,
            "manifest_version": EXPECTED_STREAM_VERSION,
        }
        await session.execute(
            text("""INSERT INTO orbit_metric_query_snapshot(
         tenant_id,id,actor_id,subject_id,auth_version,auth_fingerprint,query_hash,query_json,
         account_scope_snapshot_id,account_scope_hash,account_scope_count,source_publication_id,
         source_generation,profile_id,profile_version,profile_hash,algorithm_version,state,
         build_generation,build_token_hash,lease_until,expected_cell_count,expected_account_count,data_as_of,created_at,
         expected_unit_hash,expected_membership_hash,expected_membership_count,expected_manifest_version)
         VALUES(:tenant_id,:id,:actor_id,:subject_id,:auth_version,:auth_fingerprint,:query_hash,:query_json,
         :scope_snapshot_id,:scope_hash,:scope_count,:source_publication_id,:source_generation,:profile_id,
         :profile_version,:profile_hash,:algorithm,'BUILDING',1,:token_hash,:lease,:unit_count,:account_count,:now,:now,
         :unit_hash,:member_hash,:member_count,:manifest_version)"""),
            values,
        )
        await session.execute(
            text("""INSERT INTO orbit_metric_query_request(
         tenant_id,actor_id,key_hash,request_hash,query_id,after_ordinal,page_size,request_id,created_at)
         VALUES(:tenant,:actor,:key_hash,:request_hash,:id,0,:page_size,:request_id,:now)"""),
            {
                "tenant": metadata["tenant_id"],
                "actor": actor,
                "key_hash": key_hash,
                "request_hash": request_hash,
                "id": query_id,
                "page_size": metadata["query"]["page_size"],
                "request_id": request_id,
                "now": stamp,
            },
        )
        return MappingProxyType({"query_id": query_id, "state": "BUILDING", "replayed": False})

    async def _header(self, session, tenant, query_id, *, update=False):
        found = await rows(
            session,
            "SELECT q.* FROM orbit_metric_query_snapshot q "
            "WHERE q.tenant_id=:tenant AND q.id=:query_id "
            + ("FOR UPDATE" if update else "FOR SHARE"),
            {"tenant": tenant, "query_id": query_id},
        )
        if len(found) != 1 or found[0]["cleanup_requested"]:
            raise OrbitError(404, "NOT_FOUND", "指标查询不存在或不可读")
        return found[0]

    async def claim(self, session, actor, query_id):
        """T2先复验授权/原来源与预期根，再锁parent、清旧children、CAS新代。"""
        self._providers()
        context = await self.read.resume_persisted_query(session, actor, query_id)
        metadata, manifest = await self._manifest(session, actor, context)
        header = await self._header(session, metadata["tenant_id"], query_id, update=True)
        self._header_manifest(header, manifest)
        if header["state"] == "READY":
            return None
        if header["state"] != "BUILDING":
            raise OrbitError(
                503, "METRICS_QUERY_BUILD_FAILED", "原指标查询未完整构建，原幂等意图已保留"
            )
        stamp = now_utc(self.clock)
        if type(header["lease_until"]) is not datetime:
            unverified()
        if header["lease_until"] > stamp:
            busy()
        strict_integer(header["build_generation"], minimum=1)
        strict_hash(header["build_token_hash"])
        old = {
            "tenant": metadata["tenant_id"],
            "query_id": query_id,
            "generation": header["build_generation"],
            "token": header["build_token_hash"],
        }
        # 组合FK依赖旧generation；必须删除旧children后才能更新parent代次。
        # 每一条DELETE仍再次精确绑定持锁parent的旧nonce，迟到旧builder不能删新代。
        for table in CHILD_TABLES:
            await session.execute(
                text(
                    f"DELETE c FROM {table} c JOIN orbit_metric_query_snapshot q "
                    "ON q.tenant_id=c.tenant_id AND q.id=c.query_id "
                    "AND q.build_generation=c.build_generation "
                    "WHERE c.tenant_id=:tenant AND c.query_id=:query_id "
                    "AND c.build_generation=:generation "
                    "AND q.build_token_hash=:token AND q.state='BUILDING' AND q.cleanup_requested=0"
                ),
                old,
            )
        generation = header["build_generation"] + 1
        strict_integer(generation, minimum=1)
        token_hash = digest(secrets.token_hex(32))
        updated = await session.execute(
            text("""UPDATE orbit_metric_query_snapshot SET
         build_generation=:next_generation,build_token_hash=:next_token,lease_until=:lease,
         row_count=0,row_bytes=0,totals_count=0,missing_count=0,
         rows_hash=NULL,totals_hash=NULL,sealed_at=NULL,failure_code=NULL
         WHERE tenant_id=:tenant AND id=:query_id AND build_generation=:generation
         AND build_token_hash=:token AND state='BUILDING' AND cleanup_requested=0"""),
            old
            | {
                "next_generation": generation,
                "next_token": token_hash,
                "lease": stamp
                + timedelta(
                    seconds=max(
                        LEASE_SECONDS,
                        self.budget.max_seconds + 10
                        if type(self.budget) is ResultBuildBudget
                        else 0,
                    )
                ),
            },
        )
        if updated.rowcount != 1:
            stale_claim()
        connection = await session.connection()
        ticket = _BuildTicket()
        self._claims[ticket] = _Claim(
            ref(connection),
            actor,
            metadata["tenant_id"],
            query_id,
            generation,
            token_hash,
            manifest,
        )
        return ticket

    async def _claim(self, session, ticket):
        self._providers()
        transaction(session)
        if type(ticket) is not _BuildTicket or ticket not in self._claims:
            stale_claim()
        claim = self._claims[ticket]
        if claim.connection() is not await session.connection():
            stale_claim()
        return claim

    async def fail(self, session, ticket, code):
        """仅当前代际写固定安全失败码；失败不会自动另建query或换source。"""
        claim = await self._claim(session, ticket)
        if code not in {
            "METRICS_DATA_UNVERIFIED",
            "METRICS_RESOURCE_LIMIT",
            "METRICS_BUILD_CANCELLED",
        }:
            raise ValueError("构建失败码必须为固定安全枚举")
        updated = await session.execute(
            text("""UPDATE orbit_metric_query_snapshot
         SET state='FAILED',failure_code=:code WHERE tenant_id=:tenant AND id=:query_id
         AND build_generation=:generation AND build_token_hash=:token
         AND state='BUILDING' AND cleanup_requested=0"""),
            {
                "tenant": claim.tenant,
                "query_id": claim.query_id,
                "generation": claim.generation,
                "token": claim.token_hash,
                "code": code,
            },
        )
        if updated.rowcount != 1:
            stale_claim()

    async def stage_inputs(self, session, ticket):
        """在同连接事务内完整装载独立预期与固定来源；坏包不返回可发布票据。"""
        claim = await self._claim(session, ticket)
        if type(self.budget) is not ResultBuildBudget:
            unverified()
        context = await self.read.resume_persisted_query(session, claim.actor, claim.query_id)
        metadata, manifest = await self._manifest(session, claim.actor, context)
        if manifest != claim.manifest:
            unverified()
        header = await self._header(session, claim.tenant, claim.query_id)
        self._header_manifest(header, manifest)
        stage = _TemporaryStage(await session.connection())
        try:
            unit_name = await stage.create(
                "unit",
                """(
             account_id CHAR(36) NOT NULL,business_date DATE NOT NULL,
             owner_user_id CHAR(36) NULL,owner_team_id CHAR(36) NULL,currency CHAR(3) NOT NULL,
             timezone_name VARCHAR(64) NOT NULL,account_snapshot_id CHAR(36) NOT NULL,
             attribution_version BIGINT NOT NULL,entity_count BIGINT NOT NULL,
             entity_hash CHAR(64) NOT NULL,members_verified BOOLEAN NOT NULL DEFAULT 0,
             payload_json JSON NOT NULL,PRIMARY KEY(account_id,business_date))
             ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs""",
            )
            member_name = await stage.create(
                "member",
                """(
             account_id CHAR(36) NOT NULL,business_date DATE NOT NULL,entity_id CHAR(36) NOT NULL,
             entity_snapshot_id CHAR(36) NOT NULL,name_capture_sequence BIGINT NOT NULL,
             name_observed_at DATETIME(6) NOT NULL,PRIMARY KEY(account_id,business_date,entity_id),
             KEY idx_member_entity(entity_id,account_id,business_date))
             ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_as_cs""",
            )
            for kind, original in (
                ("cell", "orbit_metric_capture_cell"),
                ("fact", "orbit_metric_ad_fact_version"),
                ("dimension", "orbit_metric_entity_snapshot"),
            ):
                await stage.create(kind, f"LIKE {original}")
            scope = await authorize_metric_scope(
                session, claim.actor, metadata["scope_snapshot_id"]
            )
            unit_check = ExpectedStreamVerifier(manifest)
            async for batch in self.expected_provider.iter_unit_batches(
                session, scope, metadata["query"], manifest
            ):
                unit_check.add(batch)
                self._charge(stage, [item.record() for item in batch])
                bindings = []
                for unit in batch:
                    # Provider冻结的历史归属仍必须满足当前请求的真实数据范围。
                    allowed = (
                        scope.current.data_role == "SUPER_ADMIN"
                        or unit.owner_user_id == scope.current.subject_id
                        or (
                            scope.current.data_role == "TEAM_ADMIN"
                            and unit.owner_team_id in scope.managed_team_ids
                        )
                    )
                    operator = metadata["query"]["operator_user_id"]
                    if not allowed or (operator is not None and unit.owner_user_id != operator):
                        unverified()
                    if len(unit.timezone_name) > 64:
                        unverified()
                    # 缺失cell的日期也必须按独立冻结账户时区拒绝未来日。
                    validate_account_local_today(
                        metadata["query"],
                        now_utc(self.clock)
                        .replace(tzinfo=UTC)
                        .astimezone(ZoneInfo(unit.timezone_name))
                        .date(),
                    )
                    values = {
                        "account": unit.account_id,
                        "day": unit.business_date,
                        "owner": unit.owner_user_id,
                        "team": unit.owner_team_id,
                        "currency": unit.currency,
                        "timezone": unit.timezone_name,
                        "snapshot": unit.account_snapshot_id,
                        "version": unit.attribution_version,
                        "count": unit.entity_count,
                        "hash": unit.entity_hash,
                        "verified": 1,
                        "payload": canonical(unit.record()),
                        "tenant": claim.tenant,
                    }
                    if unit.entity_count == 0 and unit.entity_hash != hashlib.sha256().hexdigest():
                        unverified()
                    if metadata["query"]["dataset"] == "ACCOUNT" and unit.entity_count != 1:
                        unverified()
                    bindings.append(values)
                await session.execute(
                    text(
                        f"INSERT INTO {unit_name} VALUES "
                        "(:account,:day,:owner,:team,:currency,:timezone,:snapshot,"
                        ":version,:count,:hash,:verified,:payload)"
                    ),
                    bindings,
                )
            unit_check.finish()
            scope_sql = ""
            scope_values = {"tenant": claim.tenant}
            if scope.snapshot_id is not None:
                scope_sql = (
                    " OR NOT EXISTS(SELECT 1 FROM orbit_account_scope_member m "
                    "WHERE m.tenant_id=:tenant AND m.snapshot_id=:scope "
                    "AND m.account_id=u.account_id)"
                )
                scope_values["scope"] = scope.snapshot_id
            bad_units = await rows(
                session,
                f"SELECT u.account_id FROM {unit_name} u "
                "LEFT JOIN orbit_metric_entity_snapshot d ON d.tenant_id=:tenant "
                "AND d.id=u.account_snapshot_id AND d.entity_kind='ACCOUNT' "
                "AND d.account_id=u.account_id AND d.entity_id=u.account_id "
                "WHERE d.id IS NULL" + scope_sql + " LIMIT 1",
                scope_values,
            )
            if bad_units:
                unverified()
            async for batch in self._verified_membership_batches(
                session, scope, metadata, manifest
            ):
                self._charge(stage, [item.record() for item in batch])
                if any(
                    item.name_observed_at.replace(tzinfo=None) > header["data_as_of"]
                    for item in batch
                ):
                    unverified()
                await session.execute(
                    text(
                        f"INSERT INTO {member_name} VALUES "
                        "(:account,:day,:entity,:snapshot,:sequence,:observed)"
                    ),
                    [
                        {
                            "account": member.account_id,
                            "day": member.business_date,
                            "entity": member.entity_id,
                            "snapshot": member.entity_snapshot_id,
                            "sequence": member.name_capture_sequence,
                            "observed": member.name_observed_at.replace(tzinfo=None),
                        }
                        for member in batch
                    ],
                )
            bad_members = await rows(
                session,
                f"SELECT m.entity_id FROM {member_name} m "
                "LEFT JOIN orbit_metric_entity_snapshot d ON d.tenant_id=:tenant "
                "AND d.id=m.entity_snapshot_id AND d.account_id=m.account_id "
                "AND d.entity_kind=:kind AND d.entity_id=m.entity_id WHERE d.id IS NULL LIMIT 1",
                {"tenant": claim.tenant, "kind": metadata["query"]["dataset"]},
            )
            if bad_members:
                unverified()
            async for cells in self.read.iter_latest_cells(session, context):
                if any(item["oldest_observed_at"] > header["data_as_of"] for item in cells.rows):
                    unverified()
                self._charge(stage, cells.rows)
                await self._insert_raw(session, stage.names["cell"], cells.rows)
                if metadata["query"]["dataset"] == "ACCOUNT":
                    dimensions = await self.read.select_dimensions(session, context, cells)
                    self._charge(stage, dimensions)
                    await self._insert_raw(session, stage.names["dimension"], dimensions)
                async for facts in self.read.iter_selected_facts(session, context, cells):
                    if any(item["observed_at"] > header["data_as_of"] for item in facts.rows):
                        unverified()
                    self._charge(stage, facts.rows)
                    await self._insert_raw(session, stage.names["fact"], facts.rows)
                    if metadata["query"]["dataset"] != "ACCOUNT":
                        dimensions = await self.read.select_dimensions(session, context, facts)
                        self._charge(stage, dimensions)
                        await self._insert_raw(session, stage.names["dimension"], dimensions)
            # 缺失事实也保留独立预期真实历史名称，不用当前目录填空。
            await session.execute(
                text(
                    f"INSERT IGNORE INTO {stage.names['dimension']} "
                    "SELECT d.* FROM orbit_metric_entity_snapshot d JOIN "
                    f"{member_name} m ON m.entity_snapshot_id=d.id WHERE d.tenant_id=:tenant"
                ),
                {"tenant": claim.tenant},
            )
            await self._describe(session, context)
            checked = await self.expected_provider.revalidate_manifest(
                session, scope, metadata["query"], manifest
            )
            if type(checked) is not ExpectedUnitManifest or checked != manifest:
                unverified()
            handle = _StageTicket()
            metadata = MappingProxyType(
                dict(metadata)
                | {
                    "data_as_of": header["data_as_of"],
                    "expected_account_count": header["expected_account_count"],
                }
            )
            self._stages[handle] = (ticket, stage, metadata)
            return handle
        except BaseException:
            try:
                await stage.close()
            except BaseException:
                pass  # close已使不确定连接失效，保留最初的业务/取消异常。
            raise

    async def _verified_membership_batches(self, session, scope, metadata, manifest):
        """两个受信有界有序流归并，逐unit核成员根，不做N次数据库lookup。"""
        units_check = ExpectedStreamVerifier(manifest)

        async def unit_items():
            async for chunk in self.expected_provider.iter_unit_batches(
                session, scope, metadata["query"], manifest
            ):
                units_check.add(chunk)
                for value in chunk:
                    yield value
            units_check.finish()

        iterator = unit_items()
        selected = await anext(iterator, None)
        per_unit = None
        members_check = ExpectedStreamVerifier(manifest, memberships=True)
        async for batch in self.expected_provider.iter_membership_batches(
            session, scope, metadata["query"], manifest
        ):
            members_check.add(batch)
            for member in batch:
                key = member.key()[:2]
                while selected is not None and selected.key() < key:
                    if per_unit is not None:
                        per_unit.finish()
                    elif (
                        selected.entity_count != 0
                        or selected.entity_hash != hashlib.sha256().hexdigest()
                    ):
                        unverified()
                    selected, per_unit = await anext(iterator, None), None
                if selected is None or selected.key() != key:
                    unverified()
                if per_unit is None:
                    per_unit = ExpectedStreamVerifier(manifest, memberships=True, unit=selected)
                per_unit.add((member,))
            yield batch
        members_check.finish()
        while selected is not None:
            if per_unit is not None:
                per_unit.finish()
            elif selected.entity_count != 0 or selected.entity_hash != hashlib.sha256().hexdigest():
                unverified()
            selected, per_unit = await anext(iterator, None), None

    @staticmethod
    async def _insert_raw(session, table, batch):
        if not batch:
            return
        if not 1 <= len(batch) <= 200:
            unverified()
        columns = tuple(batch[0])
        if any(re.fullmatch(r"[a-z_]+", key) is None for key in columns):
            unverified()
        if any(tuple(item) != columns for item in batch):
            unverified()
        identifiers = ",".join(columns)
        bindings = ",".join(":" + key for key in columns)
        equal = " AND ".join(f"({key}<=>VALUES({key}))" for key in columns)
        # 克隆表的不可变主键已约束来源；重复必须完整原文相同，不能只比较hash。
        await session.execute(
            text(
                f"INSERT INTO {table} ({identifiers}) VALUES ({bindings}) "
                f"ON DUPLICATE KEY UPDATE id=IF({equal},id,NULL)"
            ),
            [dict(item) for item in batch],
        )

    def _charge(self, stage, batch):
        def encode(value):
            if isinstance(value, (date, datetime)):
                return value.isoformat()
            unverified()

        try:
            records = [dict(item) if hasattr(item, "items") else item for item in batch]
            encoded = json.dumps(
                records,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=encode,
                allow_nan=False,
            ).encode()
        except (ValueError, TypeError, UnicodeError):
            unverified()
        stage.input_rows += len(batch)
        stage.input_bytes += len(encoded)
        if (
            stage.input_rows > self.budget.max_input_rows
            or stage.input_bytes > self.budget.max_input_bytes
        ):
            raise OrbitError(503, "METRICS_RESOURCE_LIMIT", "指标输入超出内部构建资源预算")

    async def aggregate_stage(self, session, handle):
        """SQL先固定全窗口匹配实体，再逐组有界投影；不在Python收集全部结果。"""
        self._providers()
        if type(handle) is not _StageTicket or handle not in self._stages:
            stale_claim()
        ticket, stage, metadata = self._stages[handle]
        await self._claim(session, ticket)
        query = metadata["query"]
        n = stage.names
        dataset = query["dataset"].lower()
        if dataset not in {"account", "campaign", "adset", "ad"}:
            unverified()
        # 独立预期与实际完整cell必须同一历史归属版本，不能把漂移当缺失继续出包。
        mismatches = await rows(
            session,
            f"""SELECT COUNT(*) AS count FROM {n["unit"]} u
         JOIN {n["cell"]} c ON c.account_id=u.account_id AND c.business_date=u.business_date
         WHERE NOT(c.owner_user_id<=>u.owner_user_id) OR NOT(c.owner_team_id<=>u.owner_team_id)
         OR c.currency<>u.currency OR c.timezone_name<>u.timezone_name
         OR c.account_snapshot_id<>u.account_snapshot_id
         OR c.attribution_version<>u.attribution_version""",
            {},
        )
        if mismatches[0]["count"]:
            unverified()
        values = []
        for bit, field in enumerate(VALUE_NAMES):
            values.append(
                f"CASE WHEN f.id IS NOT NULL THEN f.{field} "
                "WHEN c.id IS NOT NULL AND c.empty_result=1 "
                f"AND (c.empty_field_mask & {1 << bit})<>0 "
                f"THEN CAST(0 AS DECIMAL(34,6)) ELSE NULL END AS {field}"
            )
        await stage.create(
            "contribution",
            f"""(
         KEY idx_contribution_group(entity_id,currency,business_date,account_id),
         KEY idx_contribution_unit(account_id,business_date)) ENGINE=InnoDB AS
         SELECT m.entity_id,u.currency,u.account_id,u.business_date,f.ad_id,
          u.owner_user_id,u.owner_team_id,f.channel_id,f.product_name_snapshot,
          d.id AS dimension_id,
          COALESCE(c.capture_sequence,m.name_capture_sequence) AS capture_sequence,
          c.oldest_observed_at,
          COALESCE(f.observed_at,c.oldest_observed_at,m.name_observed_at) AS name_observed,
          IF(c.id IS NOT NULL AND (f.id IS NOT NULL OR c.empty_result=1),1,0) AS unit_complete,
          COALESCE(c.critical_complete,0) AS critical_complete,{",".join(values)}
         FROM {n["member"]} m JOIN {n["unit"]} u
          ON u.account_id=m.account_id AND u.business_date=m.business_date
         LEFT JOIN {n["cell"]} c ON c.account_id=u.account_id AND c.business_date=u.business_date
         LEFT JOIN {n["fact"]} f ON f.cell_id=c.id AND f.{dataset}_id=m.entity_id
         JOIN {n["dimension"]} d ON d.id=COALESCE(f.{dataset}_snapshot_id,m.entity_snapshot_id)
         """.replace("f.account_id=m.entity_id", "f.account_id=m.entity_id"),
        )
        # MySQL不能在同一语句重开同一TEMP表，因此各阶段物化一次，不用自连接临时表。
        await stage.create(
            "matched",
            f"""(PRIMARY KEY(entity_id,currency)) ENGINE=InnoDB AS
         SELECT ranked.entity_id,ranked.currency FROM (
          SELECT x.entity_id,x.currency,d.name,d.external_id,
           ROW_NUMBER() OVER(PARTITION BY x.entity_id,x.currency ORDER BY x.business_date DESC,
            COALESCE(x.capture_sequence,0) DESC,x.name_observed DESC,x.dimension_id DESC) AS rank_no
          FROM {n["contribution"]} x JOIN {n["dimension"]} d ON d.id=x.dimension_id
         ) ranked WHERE ranked.rank_no=1 AND (
          :empty_q=1 OR ranked.name LIKE :contains ESCAPE '!' OR
          (:numeric_q=1 AND ranked.external_id=:external_id))""",
            {
                "empty_q": int(not query["q"]),
                "contains": literal_contains(query["q"]),
                "numeric_q": int(re.fullmatch(r"[0-9]{1,64}", query["q"]) is not None),
                "external_id": query["q"] if re.fullmatch(r"[0-9]{1,64}", query["q"]) else "",
            },
        )
        # CREATE AS SELECT含参数需沿execute绑定；create不接受请求文本插值。
        # 上一步用的全是固定占位符，实际绑定由stage的受控参数入口完成。
        await stage.create(
            "filtered",
            f"""(
         KEY idx_filtered_group(entity_id,currency,business_date,account_id),
         KEY idx_filtered_unit(account_id,business_date)) ENGINE=InnoDB AS
         SELECT x.* FROM {n["contribution"]} x JOIN {n["matched"]} m
          ON m.entity_id=x.entity_id AND m.currency=x.currency""",
        )
        day = "x.business_date" if query["granularity"] == "DAY" else "DATE('1000-01-01')"
        nullable = []
        for source, target in (
            ("owner_user_id", "operator_user_id"),
            ("owner_team_id", "owner_team_id"),
            ("channel_id", "channel_id"),
            ("product_name_snapshot", "product_name_snapshot"),
        ):
            nullable.append(
                f"CASE WHEN COUNT(x.{source})=COUNT(*) AND MIN(BINARY x.{source})="
                f"MAX(BINARY x.{source}) THEN MIN(x.{source}) ELSE NULL END AS {target}"
            )
        await stage.create(
            "group_count",
            f"""(PRIMARY KEY(entity_id,currency,group_day)) ENGINE=InnoDB AS
         SELECT x.entity_id,x.currency,{day} AS group_day,
          COUNT(DISTINCT x.account_id) AS account_count,
          COUNT(DISTINCT x.account_id,x.ad_id) AS ad_count,{",".join(nullable)}
         FROM {n["filtered"]} x GROUP BY x.entity_id,x.currency,{day}""",
        )
        await stage.create(
            "display",
            f"""(PRIMARY KEY(entity_id,currency,group_day)) ENGINE=InnoDB AS
         SELECT entity_id,currency,group_day,dimension_id,business_date,
          capture_sequence,name_observed
         FROM (SELECT x.entity_id,x.currency,{day} AS group_day,x.dimension_id,x.business_date,
          COALESCE(x.capture_sequence,0) AS capture_sequence,x.name_observed,
          ROW_NUMBER() OVER(PARTITION BY x.entity_id,x.currency,{day} ORDER BY x.business_date DESC,
           COALESCE(x.capture_sequence,0) DESC,x.name_observed DESC,x.dimension_id DESC) AS rank_no
          FROM {n["filtered"]} x) ranked WHERE rank_no=1""",
        )
        summed = ",".join(
            f"CASE WHEN COUNT(x.{field})=COUNT(*) THEN SUM(x.{field}) ELSE NULL END AS {field}"
            for field in VALUE_NAMES
        )
        await stage.create(
            "unit_sum",
            f"""(
         PRIMARY KEY(entity_id,currency,group_day,account_id,business_date)) ENGINE=InnoDB AS
         SELECT x.entity_id,x.currency,{day} AS group_day,x.account_id,x.business_date,
          MIN(x.unit_complete) AS unit_complete,MIN(x.critical_complete) AS critical_complete,
          MIN(x.oldest_observed_at) AS observed_at,{summed}
         FROM {n["filtered"]} x
         GROUP BY x.entity_id,x.currency,{day},x.account_id,x.business_date""",
        )
        # 原始事实流按cell有界物化；筛选无匹配不能抹掉采集完成状态，
        # 也不能把未读取完整cell或原字段缺失伪装为有效零。
        field_counts = ",".join(f"COUNT(f.{field}) AS {field}_count" for field in VALUE_NAMES)
        await stage.create(
            "cell_field_proof",
            f"""(PRIMARY KEY(cell_id)) ENGINE=InnoDB AS
         SELECT f.cell_id,COUNT(*) AS fact_rows,{field_counts}
         FROM {n["fact"]} f GROUP BY f.cell_id""",
        )
        derived_empty = (
            "u.members_verified=1 AND u.entity_count=0 AND c.fact_count>0 "
            "AND p.fact_rows=c.fact_count"
        )
        total_values = []
        for bit, field in enumerate(VALUE_NAMES):
            total_values.append(
                f"CASE WHEN COUNT(x.entity_id)>0 THEN CASE WHEN COUNT(x.{field})="
                f"COUNT(x.entity_id) THEN SUM(x.{field}) ELSE NULL END "
                "WHEN c.id IS NOT NULL AND c.empty_result=1 "
                f"AND (c.empty_field_mask & {1 << bit})<>0 "
                "THEN CAST(0 AS DECIMAL(65,6)) "
                f"WHEN c.id IS NOT NULL AND {derived_empty} "
                f"AND p.{field}_count=c.fact_count "
                f"THEN CAST(0 AS DECIMAL(65,6)) ELSE NULL END AS {field}"
            )
        await stage.create(
            "total_unit",
            f"""(
         PRIMARY KEY(currency,account_id,business_date)) ENGINE=InnoDB AS
         SELECT u.currency,u.account_id,u.business_date,
          IF(c.id IS NOT NULL,1,0) AS unit_complete,
          COALESCE(c.critical_complete,0) AS critical_complete,c.oldest_observed_at AS observed_at,
          {",".join(total_values)}
         FROM {n["unit"]} u LEFT JOIN {n["cell"]} c
          ON c.account_id=u.account_id AND c.business_date=u.business_date
         LEFT JOIN {n["filtered"]} x
          ON x.account_id=u.account_id AND x.business_date=u.business_date
         LEFT JOIN {n["cell_field_proof"]} p ON p.cell_id=c.id
         GROUP BY u.currency,u.account_id,u.business_date,c.id,c.empty_result,c.empty_field_mask,
          c.critical_complete,c.oldest_observed_at,c.fact_count,u.members_verified,u.entity_count,
          p.fact_rows,{",".join(f"p.{field}_count" for field in VALUE_NAMES)}""",
        )
        await stage.create(
            "total_count",
            f"""(PRIMARY KEY(currency)) ENGINE=InnoDB AS
         SELECT u.currency,COUNT(DISTINCT u.account_id) AS account_count,
          COUNT(DISTINCT x.account_id,x.ad_id) AS ad_count
         FROM {n["unit"]} u LEFT JOIN {n["filtered"]} x
          ON x.account_id=u.account_id AND x.business_date=u.business_date GROUP BY u.currency""",
        )
        await stage.create(
            "result",
            """(
         entity_id CHAR(36) NOT NULL,currency CHAR(3) NOT NULL,group_day DATE NOT NULL,
         payload_json JSON NOT NULL,payload_hash CHAR(64) NOT NULL,payload_bytes INT NOT NULL,
         sort_name VARBINARY(1020) NOT NULL,spend DECIMAL(65,6) NULL,
         impressions DECIMAL(65,6) NULL,clicks DECIMAL(65,6) NULL,purchases DECIMAL(65,6) NULL,
         roas DECIMAL(65,6) NULL,cpm DECIMAL(65,6) NULL,
         PRIMARY KEY(entity_id,currency,group_day)) ENGINE=InnoDB""",
        )
        await stage.create(
            "total",
            """(currency CHAR(3) NOT NULL,profile_id CHAR(36) NOT NULL,
         payload_json JSON NOT NULL,payload_hash CHAR(64) NOT NULL,
         PRIMARY KEY(currency,profile_id)) ENGINE=InnoDB""",
        )
        await self._project_rows(session, handle)
        await self._project_totals(session, handle)

    async def _project_rows(self, session, handle):
        ticket, stage, metadata = self._stages[handle]
        claim = await self._claim(session, ticket)
        n, query = stage.names, metadata["query"]
        after = ("", "", date(1000, 1, 1), "", date(1000, 1, 1))
        active_key, accumulator, output_count, output_bytes = None, None, 0, 0
        counts = None
        pending = []

        async def flush():
            if pending:
                await session.execute(
                    text(
                        f"INSERT INTO {n['result']} VALUES("
                        ":entity,:currency,:day,:payload,:hash,:bytes,:name,:spend,"
                        ":impressions,:clicks,:purchases,:roas,:cpm)"
                    ),
                    pending,
                )
                pending.clear()

        async def emit():
            nonlocal output_count, output_bytes
            payload = accumulator.finish(
                now=metadata["data_as_of"].replace(tzinfo=UTC),
                account_count=counts[0],
                ad_count=counts[1],
            )
            payload = validate_outbound(MetricRow, payload)
            encoded = canonical(payload).encode()
            output_count += 1
            output_bytes += len(encoded)
            if (
                output_count > self.budget.max_output_rows
                or output_bytes > self.budget.max_output_bytes
                or len(encoded) > 16384
            ):
                raise OrbitError(503, "METRICS_RESOURCE_LIMIT", "指标结果超出内部构建资源预算")
            values = {
                "entity": active_key[0],
                "currency": active_key[1],
                "day": active_key[2],
                "payload": encoded.decode(),
                "hash": hashlib.sha256(encoded).hexdigest(),
                "bytes": len(encoded),
                "name": payload["name"].encode(),
            }
            values.update(
                {
                    field: payload["values"][field]
                    for field in ("spend", "impressions", "clicks", "purchases", "roas", "cpm")
                }
            )
            pending.append(values)
            if len(pending) == 200:
                await flush()

        while True:
            found = await rows(
                session,
                f"""SELECT u.*,g.account_count,g.ad_count,g.owner_team_id,
             g.operator_user_id,g.channel_id,g.product_name_snapshot,d.name,
             p.dimension_id,p.business_date AS name_day,
             p.capture_sequence AS name_sequence,p.name_observed
             FROM {n["unit_sum"]} u JOIN {n["group_count"]} g
              ON g.entity_id=u.entity_id AND g.currency=u.currency AND g.group_day=u.group_day
             JOIN {n["display"]} p ON p.entity_id=u.entity_id
              AND p.currency=u.currency AND p.group_day=u.group_day
             JOIN {n["dimension"]} d ON d.id=p.dimension_id
             WHERE (u.entity_id,u.currency,u.group_day,u.account_id,u.business_date)>
              (:entity,:currency,:day,:account,:business_day)
             ORDER BY u.entity_id,u.currency,u.group_day,u.account_id,u.business_date LIMIT 200""",
                dict(
                    zip(
                        ("entity", "currency", "day", "account", "business_day"), after, strict=True
                    )
                ),
            )
            if not found:
                break
            for row in found:
                key = (row["entity_id"], row["currency"], row["group_day"])
                if key != active_key:
                    if accumulator is not None:
                        await emit()
                    active_key = key
                    accumulator = MetricResultRow(
                        ResultGroupKey(
                            claim.tenant,
                            query["dataset"],
                            key[0],
                            key[1],
                            metadata["profile_id"],
                            metadata["profile_version"],
                            key[2] if query["granularity"] == "DAY" else None,
                        )
                    )
                    accumulator.display.add(
                        DisplayContribution(
                            key[0],
                            row["name"],
                            row["name_day"],
                            row["name_sequence"],
                            row["name_observed"],
                            row["dimension_id"],
                            row["owner_team_id"],
                            row["operator_user_id"],
                            row["channel_id"],
                            row["product_name_snapshot"],
                        )
                    )
                    counts = (row["account_count"], row["ad_count"])
                accumulator.add_values(
                    MetricGroup(
                        claim.tenant, key[1], metadata["profile_id"], metadata["profile_version"]
                    ),
                    {field: numerator(row[field]) for field in VALUE_NAMES},
                )
                accumulator.coverage.add_unit(
                    complete=bool(row["unit_complete"]),
                    critical_complete=bool(row["critical_complete"]),
                    observed_at=row["observed_at"],
                )
                after = (*key, row["account_id"], row["business_date"])
            if len(found) < 200:
                break
        if accumulator is not None:
            await emit()
        await flush()

    async def _project_totals(self, session, handle):
        ticket, stage, metadata = self._stages[handle]
        claim = await self._claim(session, ticket)
        n = stage.names
        after = ("", "", date(1000, 1, 1))
        current, accumulator, count, counts = None, None, 0, None

        async def emit():
            nonlocal count
            count += 1
            if count > 1000:
                unverified()
            payload = accumulator.finish(
                now=metadata["data_as_of"].replace(tzinfo=UTC),
                account_count=counts[0],
                ad_count=counts[1],
            )
            payload = validate_outbound(MetricTotal, payload)
            encoded = canonical(payload).encode()
            if len(encoded) > 16384:
                unverified()
            await session.execute(
                text(f"INSERT INTO {n['total']} VALUES(:currency,:profile,:payload,:hash)"),
                {
                    "currency": current,
                    "profile": metadata["profile_id"],
                    "payload": encoded.decode(),
                    "hash": hashlib.sha256(encoded).hexdigest(),
                },
            )

        while True:
            found = await rows(
                session,
                f"""SELECT u.*,g.account_count,g.ad_count
             FROM {n["total_unit"]} u JOIN {n["total_count"]} g ON g.currency=u.currency
             WHERE (u.currency,u.account_id,u.business_date)>(:currency,:account,:day)
             ORDER BY u.currency,u.account_id,u.business_date LIMIT 200""",
                dict(zip(("currency", "account", "day"), after, strict=True)),
            )
            if not found:
                break
            for row in found:
                if row["currency"] != current:
                    if accumulator is not None:
                        await emit()
                    current = row["currency"]
                    accumulator = MetricResultTotal(
                        MetricGroup(
                            claim.tenant,
                            current,
                            metadata["profile_id"],
                            metadata["profile_version"],
                        )
                    )
                    counts = (row["account_count"], row["ad_count"])
                accumulator.add_values(
                    MetricGroup(
                        claim.tenant, current, metadata["profile_id"], metadata["profile_version"]
                    ),
                    {field: numerator(row[field]) for field in VALUE_NAMES},
                )
                accumulator.coverage.add_unit(
                    complete=bool(row["unit_complete"]),
                    critical_complete=bool(row["critical_complete"]),
                    observed_at=row["observed_at"],
                )
                after = (current, row["account_id"], row["business_date"])
            if len(found) < 200:
                break
        if accumulator is not None:
            await emit()

    async def publish(self, session, handle):
        """完整阶段一次发布；所有写入/晚到清理都绑定精确tenant/query/代次/nonce。"""
        if type(handle) is not _StageTicket or handle not in self._stages:
            stale_claim()
        ticket, stage, metadata = self._stages[handle]
        claim = await self._claim(session, ticket)
        context = await self.read.resume_persisted_query(session, claim.actor, claim.query_id)
        _, manifest = await self._manifest(session, claim.actor, context)
        if manifest != claim.manifest:
            unverified()
        header = await self._header(session, claim.tenant, claim.query_id, update=True)
        if (
            header["state"] != "BUILDING"
            or header["build_generation"] != claim.generation
            or header["build_token_hash"] != claim.token_hash
        ):
            stale_claim()
        self._header_manifest(header, manifest)
        n = stage.names
        # 只有每账户真实单一时区才可写049该列，不用MIN掩盖历史跨时区。
        invalid = await rows(
            session,
            f"SELECT account_id FROM {n['unit']} GROUP BY account_id "
            "HAVING COUNT(DISTINCT timezone_name)<>1 LIMIT 1",
            {},
        )
        if invalid:
            unverified()
        await self._publish_accounts(session, claim, stage, header["expected_account_count"])
        sort, direction = metadata["query"]["sort"], metadata["query"]["direction"]
        if sort not in {
            "spend",
            "impressions",
            "clicks",
            "purchases",
            "roas",
            "cpm",
            "name",
        } or direction not in {"ASC", "DESC"}:
            unverified()
        column = "sort_name" if sort == "name" else sort
        await stage.create(
            "ordered",
            f"""(PRIMARY KEY(ordinal)) ENGINE=InnoDB AS
         SELECT ROW_NUMBER() OVER(ORDER BY ({column} IS NULL) ASC,{column} {direction},
          entity_id ASC,currency ASC,group_day ASC) AS ordinal,r.* FROM {n["result"]} r""",
        )
        values = {
            "tenant": claim.tenant,
            "query_id": claim.query_id,
            "generation": claim.generation,
            "token": claim.token_hash,
        }
        await stage.create(
            "publish_row",
            """(ordinal BIGINT NOT NULL PRIMARY KEY,
         row_hash CHAR(64) NOT NULL,payload_json JSON NOT NULL,payload_hash CHAR(64) NOT NULL,
         payload_bytes INT NOT NULL) ENGINE=InnoDB""",
        )
        root, ordinal, byte_count = hashlib.sha256(), 0, 0
        while True:
            batch = await rows(
                session,
                f"SELECT * FROM {n['ordered']} WHERE ordinal>:after ORDER BY ordinal LIMIT 200",
                {"after": ordinal},
            )
            if not batch:
                break
            bindings = []
            for item in batch:
                if item["ordinal"] != ordinal + 1:
                    unverified()
                payload = self._payload(item, MetricRow)
                row_hash = digest(
                    [
                        metadata["query"]["dataset"],
                        payload["entity_id"],
                        payload["currency"],
                        payload["business_date"],
                    ]
                )
                ordinal = item["ordinal"]
                byte_count += item["payload_bytes"]
                root.update(canonical([ordinal, row_hash, item["payload_hash"]]).encode() + b"\n")
                bindings.append(
                    values
                    | {
                        "ordinal": ordinal,
                        "row_hash": row_hash,
                        "payload": canonical(payload),
                        "payload_hash": item["payload_hash"],
                        "payload_bytes": item["payload_bytes"],
                    }
                )
            await session.execute(
                text(
                    f"INSERT INTO {n['publish_row']} VALUES "
                    "(:ordinal,:row_hash,:payload,:payload_hash,:payload_bytes)"
                ),
                bindings,
            )
        inserted = await session.execute(
            text(f"""INSERT INTO orbit_metric_query_sorted_row
         SELECT :tenant,:query_id,:generation,r.ordinal,r.row_hash,
          r.payload_json,r.payload_hash,r.payload_bytes
         FROM {n["publish_row"]} r JOIN orbit_metric_query_snapshot q
          ON q.tenant_id=:tenant AND q.id=:query_id AND q.build_generation=:generation
         WHERE q.build_token_hash=:token AND q.state='BUILDING' AND q.cleanup_requested=0"""),
            values,
        )
        if inserted.rowcount != ordinal:
            stale_claim()
        total_root, total_count, missing = hashlib.sha256(), 0, 0
        total_rows = await rows(
            session, f"SELECT * FROM {n['total']} ORDER BY currency,profile_id LIMIT 1001", {}
        )
        if len(total_rows) > 1000:
            unverified()
        for item in total_rows:
            payload = self._payload(item, MetricTotal)
            missing += payload["missing_count"]
            total_count += 1
            total_root.update(
                canonical(
                    [payload["currency"], payload["metric_profile_id"], item["payload_hash"]]
                ).encode()
                + b"\n"
            )
        inserted = await session.execute(
            text(f"""INSERT INTO orbit_metric_query_total
         SELECT :tenant,:query_id,:generation,t.currency,t.profile_id,t.payload_json,t.payload_hash
         FROM {n["total"]} t JOIN orbit_metric_query_snapshot q
          ON q.tenant_id=:tenant AND q.id=:query_id AND q.build_generation=:generation
         WHERE q.build_token_hash=:token AND q.state='BUILDING' AND q.cleanup_requested=0"""),
            values,
        )
        if inserted.rowcount != total_count:
            stale_claim()
        strict_integer(missing, maximum=2147483647)
        updated = await session.execute(
            text("""UPDATE orbit_metric_query_snapshot SET
         state='READY',row_count=:rows,row_bytes=:bytes,totals_count=:totals,missing_count=:missing,
         rows_hash=:row_hash,totals_hash=:total_hash,sealed_at=:now
         WHERE tenant_id=:tenant AND id=:query_id AND build_generation=:generation
         AND build_token_hash=:token AND state='BUILDING' AND cleanup_requested=0"""),
            values
            | {
                "rows": ordinal,
                "bytes": byte_count,
                "totals": total_count,
                "missing": missing,
                "row_hash": root.hexdigest(),
                "total_hash": total_root.hexdigest(),
                "now": now_utc(self.clock),
            },
        )
        if updated.rowcount != 1:
            stale_claim()

    async def _publish_accounts(self, session, claim, stage, expected_count):
        previous, account, timezone, root, count = ("", date(1000, 1, 1)), None, None, None, 0
        table = await stage.create(
            "accountproof",
            """(account_id CHAR(36) NOT NULL PRIMARY KEY,
         timezone_name VARCHAR(64) NOT NULL,expectation_hash CHAR(64) NOT NULL) ENGINE=InnoDB""",
        )
        pending = []

        async def flush():
            if pending:
                await session.execute(
                    text(f"INSERT INTO {table} VALUES(:account,:timezone,:hash)"), pending
                )
                pending.clear()

        async def emit():
            nonlocal count
            count += 1
            pending.append({"account": account, "timezone": timezone, "hash": root.hexdigest()})
            if len(pending) == 200:
                await flush()

        while True:
            batch = await rows(
                session,
                f"SELECT * FROM {stage.names['unit']} WHERE "
                "(account_id,business_date)>(:account,:day) "
                "ORDER BY account_id,business_date LIMIT 200",
                {"account": previous[0], "day": previous[1]},
            )
            if not batch:
                break
            for item in batch:
                if item["account_id"] != account:
                    if account is not None:
                        await emit()
                    account, timezone, root = (
                        item["account_id"],
                        item["timezone_name"],
                        hashlib.sha256(),
                    )
                raw = item["payload_json"]
                raw = json.loads(raw) if type(raw) is str else raw
                root.update(canonical(raw).encode() + b"\n")
                previous = (item["account_id"], item["business_date"])
            if len(batch) < 200:
                break
        if account is not None:
            await emit()
        if type(expected_count) is not int or count != expected_count:
            unverified()
        await flush()
        inserted = await session.execute(
            text(f"""INSERT INTO orbit_metric_query_expected_account
         SELECT :tenant,:query_id,:generation,a.account_id,a.timezone_name,a.expectation_hash
         FROM {table} a JOIN orbit_metric_query_snapshot q
          ON q.tenant_id=:tenant AND q.id=:query_id AND q.build_generation=:generation
         WHERE q.build_token_hash=:token AND q.state='BUILDING' AND q.cleanup_requested=0"""),
            {
                "tenant": claim.tenant,
                "query_id": claim.query_id,
                "generation": claim.generation,
                "token": claim.token_hash,
            },
        )
        if inserted.rowcount != count:
            stale_claim()

    @staticmethod
    def _payload(item, model):
        raw = item["payload_json"]
        try:
            value = json.loads(raw) if type(raw) is str else raw
            value = validate_outbound(model, value)
            encoded = canonical(value).encode()
            if hashlib.sha256(encoded).hexdigest() != item["payload_hash"]:
                unverified()
            if "payload_bytes" in item and item["payload_bytes"] != len(encoded):
                unverified()
            return value
        except (ValueError, TypeError, UnicodeError, KeyError):
            unverified()

    async def page(self, session, actor, query_id, body, authorization):
        """T3实时重验原scope/profile/source后只读冻结ordinal；不重新扫描事实。"""
        self._providers()
        if not isinstance(self.tokens, DirectoryTokens):
            unverified()
        parsed = parse_metric_query(canonical(body).encode())
        context = await self.read.resume_persisted_query(session, actor, query_id)
        metadata, manifest = await self._manifest(session, actor, context)
        header = await self._header(session, metadata["tenant_id"], query_id)
        self._header_manifest(header, manifest)
        if header["state"] == "BUILDING":
            busy()
        if header["state"] != "READY":
            raise OrbitError(503, "METRICS_QUERY_BUILD_FAILED", "原指标查询未完整构建")
        from orbit_api.metrics_query_store import metric_query_hash

        if metric_query_hash(parsed) != metadata["query_hash"]:
            raise OrbitError(409, "METRICS_QUERY_CHANGED", "指标查询条件与冻结游标不一致")
        session_hash = self.tokens.session_binding(authorization, actor, metadata["tenant_id"])
        binding = digest(
            [
                metadata["tenant_id"],
                actor,
                metadata["subject_id"],
                metadata["auth_version"],
                metadata["auth_fingerprint"],
                metadata["scope_snapshot_id"],
                metadata["scope_hash"],
                metadata["scope_count"],
                metadata["query_hash"],
                metadata["source_publication_id"],
                metadata["source_generation"],
                metadata["profile_hash"],
                session_hash,
            ]
        )
        after = 0
        if parsed["cursor"] is not None:
            claims = self.tokens.verify("METRICS_QUERY_CURSOR_V1", parsed["cursor"])
            if (
                set(claims) != {"v", "q", "b", "n", "kid", "exp"}
                or type(claims["v"]) is not int
                or claims["v"] != 1
                or claims["q"] != query_id
                or claims["b"] != binding
            ):
                raise OrbitError(409, "METRICS_QUERY_CHANGED", "指标游标授权或查询已变化")
            after = strict_integer(claims["n"])
        strict_integer(header["row_count"])
        if after > header["row_count"]:
            raise OrbitError(400, "TOKEN_INVALID", "游标位置不符合冻结结果范围")
        found = await rows(
            session,
            "SELECT * FROM orbit_metric_query_sorted_row WHERE "
            "tenant_id=:tenant AND query_id=:id AND build_generation=:generation "
            "AND ordinal>:after "
            "ORDER BY ordinal LIMIT :size",
            {
                "tenant": metadata["tenant_id"],
                "id": query_id,
                "generation": header["build_generation"],
                "after": after,
                "size": parsed["page_size"] + 1,
            },
        )
        selected = found[: parsed["page_size"]]
        if len(selected) != min(parsed["page_size"], header["row_count"] - after):
            unverified()
        items = []
        for index, item in enumerate(selected, after + 1):
            if item["ordinal"] != index:
                unverified()
            payload = self._payload(item, MetricRow)
            if item["row_key_hash"] != digest(
                [
                    parsed["dataset"],
                    payload["entity_id"],
                    payload["currency"],
                    payload["business_date"],
                ]
            ):
                unverified()
            items.append(payload)
        next_cursor = (
            self.tokens.issue(
                "METRICS_QUERY_CURSOR_V1",
                {"v": 1, "q": query_id, "b": binding, "n": selected[-1]["ordinal"]},
            )
            if len(found) > len(selected)
            else None
        )
        total_rows = await rows(
            session,
            "SELECT * FROM orbit_metric_query_total WHERE "
            "tenant_id=:tenant AND query_id=:id AND build_generation=:generation "
            "ORDER BY currency,profile_id LIMIT 1001",
            {
                "tenant": metadata["tenant_id"],
                "id": query_id,
                "generation": header["build_generation"],
            },
        )
        if len(total_rows) != header["totals_count"] or len(total_rows) > 1000:
            unverified()
        totals = [self._payload(item, MetricTotal) for item in total_rows]
        total_root = hashlib.sha256()
        for item, payload in zip(total_rows, totals, strict=True):
            total_root.update(
                canonical(
                    [payload["currency"], payload["metric_profile_id"], item["payload_hash"]]
                ).encode()
                + b"\n"
            )
        if total_root.hexdigest() != header["totals_hash"]:
            unverified()
        return metrics_page(
            source=manifest.source,
            query_snapshot_id=query_id,
            scope_version=metadata["auth_version"],
            data_as_of=header["data_as_of"].replace(tzinfo=UTC),
            missing_count=header["missing_count"],
            items=items,
            totals=totals,
            next_cursor=next_cursor,
            page_size=parsed["page_size"],
        )

    async def run(self, engine, actor, body, key, request_id, authorization):
        """唯一拥有连接的完整内部入口；暂未接原公共POST，不产生任何平台动作。"""
        self._providers()
        if type(self.budget) is not ResultBuildBudget or not isinstance(
            self.tokens, DirectoryTokens
        ):
            unverified()
        async with _owned_result_connection(engine) as connection:
            async with AsyncSession(bind=connection, expire_on_commit=False) as session:
                async with session.begin():
                    async with asyncio.timeout(self.budget.max_seconds):
                        intent = await self.prepare(
                            session, actor, body, key, request_id, authorization
                        )
                handle, ticket, published = None, None, False
                try:
                    if intent["state"] == "BUILDING":
                        async with session.begin():
                            async with asyncio.timeout(self.budget.max_seconds):
                                ticket = await self.claim(session, actor, intent["query_id"])
                        if ticket is not None:
                            async with session.begin():
                                async with asyncio.timeout(self.budget.max_seconds):
                                    handle = await self.stage_inputs(session, ticket)
                                    await self.aggregate_stage(session, handle)
                                    await self.publish(session, handle)
                            published = True
                    async with session.begin():
                        async with asyncio.timeout(self.budget.max_seconds):
                            return await self.page(
                                session, actor, intent["query_id"], body, authorization
                            )
                except BaseException as error:
                    await session.rollback()
                    if ticket is not None and not published and not connection.invalidated:
                        code = (
                            "METRICS_BUILD_CANCELLED"
                            if isinstance(error, asyncio.CancelledError)
                            else "METRICS_RESOURCE_LIMIT"
                            if isinstance(error, TimeoutError)
                            or (
                                isinstance(error, OrbitError)
                                and error.code == "METRICS_RESOURCE_LIMIT"
                            )
                            else "METRICS_DATA_UNVERIFIED"
                        )
                        try:
                            async with asyncio.timeout(5):
                                async with session.begin():
                                    await self.fail(session, ticket, code)
                        except BaseException:
                            # 不覆盖原失败，不输出SQL/参数；不确定连接不得回池。
                            try:
                                if not connection.invalidated and not connection.closed:
                                    connection.sync_connection.detach()
                            except BaseException:
                                pass
                            try:
                                async with asyncio.timeout(1):
                                    await connection.invalidate()
                            except BaseException:
                                pass
                    raise
                finally:
                    if handle is not None:
                        stage = self._stages.pop(handle)[1]
                        failed = sys.exc_info()[0] is not None
                        try:
                            await stage.close()
                        except BaseException:
                            if not failed:
                                raise
