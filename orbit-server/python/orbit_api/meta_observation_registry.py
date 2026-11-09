"""原始Meta观察登记：纯准备、当前授权、版本CAS与同事务小行写入。

不联网、不解密、不改账户或023身份；返回值必须在外层commit后才可对外展示。
历史成功键只重核当前动作与原账户范围，不因来源换版重绑历史证据。
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import bindparam, text

from orbit_api import meta_bound_observation as binding
from orbit_api.account_access import clock, parameters
from orbit_api.authorization import require_business_access
from orbit_api.configuration_store import _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.meta_launch_observation import (
    SAFE_INTEGER,
    MetaAccountObservation,
    MetaIdentityObservation,
    MetaLaunchObservation,
    MetaObservationFailure,
    external_id,
    optional_text,
)
from orbit_api.reference_access import managed_teams

MAX_BYTES = 32 * 1024 * 1024
BATCH_BYTES = 256 * 1024
OPERATION = "META_RAW_REGISTER_V1"
_ISSUER = object()


def invalid():
    raise OrbitError(503, "META_RAW_OBSERVATION_INVALID", "原始观察绑定或正文不完整") from None


def stale():
    raise OrbitError(409, "META_RAW_SOURCE_CHANGED", "账户或来源已变化，请重新只读观察") from None


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def number(value, maximum=SAFE_INTEGER, *, minimum=1):
    if type(value) is not int or not minimum <= value <= maximum:
        invalid()
    return value


def instant(value):
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset().total_seconds() != 0
    ):
        invalid()
    return value


def uuid_value(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            invalid()
    except ValueError:
        invalid()
    return value


def database_time(value):
    if not isinstance(value, datetime):
        invalid()
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def json_value(value):
    """数据库JSON解码错误只变固定类别，不输出正文。"""
    try:
        return _decode(value)
    except (TypeError, ValueError, UnicodeError):
        invalid()


@dataclass(frozen=True, repr=False)
class RawAccount:
    account_id: str
    revision: int
    external_id: str
    owner_user_id: str
    owner_team_id: str
    metadata_json: str
    edges_json: str
    unknown_json: str
    resource_count: int
    row_hash: str


@dataclass(frozen=True, repr=False)
class RawResource:
    account_id: str
    kind: str
    external_id: str
    name: str | None
    row_hash: str


@dataclass(frozen=True, repr=False)
class PreparedMetaObservation:
    bound: binding.BoundMetaObservation = field(repr=False)
    accounts: tuple[RawAccount, ...]
    resources: tuple[RawResource, ...]
    intent_hash: str
    stored_bytes: int
    _issuer: object = field(repr=False, compare=False)


def metadata(value):
    try:
        result = json.loads(value, parse_constant=lambda _: invalid())
    except (ValueError, TypeError, UnicodeError):
        invalid()
    expected = {"name", "currency", "timezone_name", "account_status", "capabilities", "user_tasks"}
    if (
        not isinstance(result, dict)
        or set(result) != expected
        or canonical(result).encode() != value
    ):
        invalid()
    for name in ("name", "currency", "timezone_name"):
        optional_text(result[name])
    if result["account_status"] is not None:
        number(result["account_status"], minimum=0)
    for name in ("capabilities", "user_tasks"):
        items = result[name]
        if items is not None:
            if not isinstance(items, list) or len(items) > 500:
                invalid()
            if any(not isinstance(item, str) or not 1 <= len(item) <= 128 for item in items):
                invalid()
            for item in items:
                optional_text(item)
            if items != sorted(set(items)):
                invalid()
    return result


def observation_tokens(observation):
    """精确复用原canonical键序，逐账户/逐资源输出，不构造全包嵌套副本。"""
    yield '{"accounts":['
    for index, account in enumerate(observation.accounts):
        if index:
            yield ","
        yield '{"bm_edges":' + canonical(account.bm_edges)
        yield ',"external_id":' + canonical(account.external_id)
        yield ',"metadata":' + account.metadata_json.decode("utf-8")
        yield ',"resources":['
        for ordinal, resource in enumerate(account.resources):
            if ordinal:
                yield ","
            yield canonical(
                {"kind": resource.kind, "external_id": resource.external_id, "name": resource.name}
            )
        yield '],"unknown_fields":' + canonical(account.unknown_fields) + "}"
    yield '],"api_version":' + canonical(observation.api_version)
    yield ',"business_id":' + canonical(observation.business_id)
    yield ',"observed_at":' + canonical(observation.observed_at.isoformat())
    yield ',"source_config_id":' + canonical(observation.source_config_id)
    yield ',"source_config_revision":' + canonical(observation.source_config_revision)
    yield ',"started_at":' + canonical(observation.started_at.isoformat()) + "}"


def stream_digest(observation):
    hasher, size = hashlib.sha256(), 0
    for token in observation_tokens(observation):
        encoded = token.encode("utf-8")
        size += len(encoded)
        if size > MAX_BYTES:
            invalid()
        hasher.update(encoded)
    return hasher.hexdigest()


def prepare_rows(bound):
    if not isinstance(bound, binding.BoundMetaObservation):
        invalid()
    source, observed = bound.source, bound.observation
    if (
        not isinstance(source, binding.MetaSourceSnapshot)
        or source._issuer is not binding._ISSUER
        or source.permission != "accounts.sync"
        or binding.binding_hash(source) != source.binding_sha256
        or not isinstance(observed, MetaLaunchObservation)
        or observed.complete is not True
        or observed.execution_authorized is not False
        or observed.policy_version is not None
        or observed.workflow_version is not None
        or bound.durable
        or bound.publication_revalidated
        or bound.execution_authorized
    ):
        invalid()
    source.configuration.validate()
    for value in (source.tenant_id, source.subject_id, source.team_id):
        uuid_value(value)
    number(source.actor_id, 2**63 - 1)
    for value in (source.auth_version, source.account_clock):
        number(value)
    if source.data_role not in {"USER", "TEAM_ADMIN", "SUPER_ADMIN"}:
        invalid()
    if (
        observed.source_config_id != source.configuration.source_config_id
        or observed.source_config_revision != source.configuration.source_config_revision
        or observed.business_id != source.configuration.business_id
        or observed.api_version != source.configuration.api_version
        or not instant(source.captured_at)
        <= instant(observed.started_at)
        <= instant(observed.observed_at)
    ):
        invalid()
    number(observed.request_count, 2500)
    number(observed.response_bytes, MAX_BYTES)
    if not isinstance(source.accounts, tuple) or not 1 <= len(source.accounts) <= 500:
        invalid()
    if not isinstance(observed.accounts, tuple) or len(observed.accounts) != len(source.accounts):
        invalid()
    bindings = {item.external_id: item for item in source.accounts}
    if len(bindings) != len(source.accounts) or len(
        {item.account_id for item in source.accounts}
    ) != len(bindings):
        invalid()
    if tuple(item.external_id for item in observed.accounts) != tuple(sorted(bindings)):
        invalid()
    for item in source.accounts:
        if not isinstance(item, binding.MetaAccountBinding):
            invalid()
        for value in (item.account_id, item.owner_user_id, item.owner_team_id):
            uuid_value(value)
        number(item.account_revision)
        external_id(item.external_id)
    # 小头/ledger/audit/outbox的规范参数预留64KiB，明细按完整参数字节精确累计。
    accounts, resources, stored = [], [], 65536
    base = {"tenant": source.tenant_id, "registry": "0" * 36}
    for account in observed.accounts:
        if not isinstance(account, MetaAccountObservation):
            invalid()
        captured = bindings[external_id(account.external_id)]
        data = metadata(account.metadata_json)
        secret = source.configuration.token
        texts = [value for value in data.values() if isinstance(value, str)]
        for key in ("capabilities", "user_tasks"):
            texts.extend(data[key] or [])
        if any(secret in value for value in texts):
            invalid()
        if (
            not isinstance(account.bm_edges, tuple)
            or not account.bm_edges
            or account.bm_edges != tuple(sorted(set(account.bm_edges)))
            or not set(account.bm_edges) <= {"owned_ad_accounts", "client_ad_accounts"}
        ):
            invalid()
        if not isinstance(account.resources, tuple) or len(account.resources) > 5000:
            invalid()
        seen, expected_unknown = set(), [key for key, value in data.items() if value is None]
        previous = None
        for item in account.resources:
            if not isinstance(item, MetaIdentityObservation) or item.kind not in {
                "PAGE",
                "PIXEL",
                "APPLICATION",
            }:
                invalid()
            key = (item.kind, external_id(item.external_id))
            if key in seen or (previous is not None and previous > key):
                invalid()
            seen.add(key)
            previous = key
            optional_text(item.name)
            if item.name is not None and secret in item.name:
                invalid()
            if item.name is None:
                expected_unknown.append(item.kind + ":" + item.external_id + ":name")
            row = {
                "account_id": captured.account_id,
                "kind": item.kind,
                "external_id": item.external_id,
                "name": item.name,
            }
            row_hash = digest(row)
            stored += len(canonical(base | row | {"row_hash": row_hash}).encode())
            if stored > MAX_BYTES:
                invalid()
            resources.append(RawResource(**row, row_hash=row_hash))
        if account.unknown_fields != tuple(sorted(expected_unknown)):
            invalid()
        row = {
            "account_id": captured.account_id,
            "revision": captured.account_revision,
            "external_id": captured.external_id,
            "owner_user_id": captured.owner_user_id,
            "owner_team_id": captured.owner_team_id,
            "metadata_json": account.metadata_json.decode(),
            "edges_json": canonical(account.bm_edges),
            "unknown_json": canonical(account.unknown_fields),
            "resource_count": len(account.resources),
        }
        row_hash = digest(row)
        stored += len(canonical(base | row | {"row_hash": row_hash}).encode())
        if stored > MAX_BYTES:
            invalid()
        accounts.append(RawAccount(**row, row_hash=row_hash))
    if stream_digest(observed) != observed.evidence_sha256:
        invalid()
    combined = digest([source.binding_sha256, observed.evidence_sha256])
    if combined != bound.binding_sha256:
        invalid()
    return (
        tuple(sorted(accounts, key=lambda row: row.account_id)),
        tuple(sorted(resources, key=lambda row: (row.account_id, row.kind, row.external_id))),
        stored,
    )


def row_batches(rows):
    batch, size = [], 0
    for row in rows:
        length = len(canonical(row).encode("utf-8"))
        if length > BATCH_BYTES:
            invalid()
        if batch and (len(batch) >= 100 or size + length > BATCH_BYTES):
            yield batch
            batch, size = [], 0
        batch.append(row)
        size += length
    if batch:
        yield batch


async def one(session, sql, values):
    return (await session.execute(text(sql), values)).mappings().first()


async def rows(session, sql, values, ids=None):
    statement = text(sql)
    if ids is not None:
        statement = statement.bindparams(bindparam("ids", expanding=True))
        values = values | {"ids": ids}
    return list((await session.execute(statement, values)).mappings())


class MetaObservationRegistry:
    def prepare(self, bound):
        try:
            accounts, resources, stored = prepare_rows(bound)
            intent = digest(
                [
                    "META_RAW_V1",
                    bound.binding_sha256,
                    bound.observation.request_count,
                    bound.observation.response_bytes,
                    [row.row_hash for row in accounts],
                    [row.row_hash for row in resources],
                ]
            )
            return PreparedMetaObservation(bound, accounts, resources, intent, stored, _ISSUER)
        except (
            AttributeError,
            KeyError,
            TypeError,
            ValueError,
            UnicodeError,
            MetaObservationFailure,
        ):
            invalid()

    async def visible_accounts(self, session, current, identifiers):
        managed = set(await managed_teams(session, current))
        result = []
        for offset in range(0, len(identifiers), 200):
            batch = identifiers[offset : offset + 200]
            selected = await rows(
                session,
                "SELECT id,revision,external_id,owner_user_id,owner_team_id,unbound_at "
                "FROM orbit_ad_account FORCE INDEX(PRIMARY) WHERE tenant_id=:tenant AND id IN :ids "
                "ORDER BY id FOR SHARE",
                {"tenant": current.tenant_id},
                ids=batch,
            )
            if {row["id"] for row in selected} != set(batch):
                raise OrbitError(404, "NOT_FOUND", "原始观察账户不存在或不在当前范围")
            for row in selected:
                if (
                    current.data_role != "SUPER_ADMIN"
                    and row["owner_user_id"] != current.subject_id
                    and not (current.data_role == "TEAM_ADMIN" and row["owner_team_id"] in managed)
                ):
                    raise OrbitError(404, "NOT_FOUND", "原始观察账户不存在或不在当前范围")
            result.extend(selected)
        return result

    async def replay(self, session, current, ledger, prepared):
        uuid_value(ledger["registry_id"])
        # 只核当前可见范围，不比较旧clock；到期投影仍不能按旧owner放行。
        await clock(session, current)
        original = await rows(
            session,
            "SELECT account_id FROM orbit_meta_raw_account WHERE tenant_id=:tenant "
            "AND registry_id=:registry ORDER BY account_id LIMIT 501 FOR SHARE",
            {"tenant": current.tenant_id, "registry": ledger["registry_id"]},
        )
        if not 1 <= len(original) <= 500:
            invalid()
        await self.visible_accounts(session, current, [row["account_id"] for row in original])
        if ledger["intent_hash"] != prepared.intent_hash:
            raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "同一幂等键不得改变原始观察")
        head = await one(
            session,
            "SELECT bound_sha256,intent_hash,account_count,resource_count,observed_at "
            "FROM orbit_meta_raw_head WHERE tenant_id=:tenant AND id=:registry FOR SHARE",
            {"tenant": current.tenant_id, "registry": ledger["registry_id"]},
        )
        receipt = json_value(ledger["receipt_json"])
        if (
            head is None
            or head["intent_hash"] != prepared.intent_hash
            or head["bound_sha256"] != prepared.bound.binding_sha256
        ):
            invalid()
        if (
            not isinstance(receipt, dict)
            or type(receipt.get("execution_authorized")) is not bool
            or receipt != self.receipt(prepared, ledger["registry_id"])
        ):
            invalid()
        if (
            head["account_count"] != len(prepared.accounts)
            or head["resource_count"] != len(prepared.resources)
            or database_time(head["observed_at"]) != prepared.bound.observation.observed_at
        ):
            invalid()
        await self.verify_details(session, current, ledger["registry_id"], prepared)
        return receipt

    async def verify_details(self, session, current, registry_id, prepared):
        """当前读逐行验证真实明细；不以头计数或保留的旧row_hash代替正文核验。"""
        base = {"tenant": current.tenant_id, "registry": registry_id}
        actual_accounts = await rows(
            session,
            "SELECT account_id,account_revision AS revision,external_id,owner_user_id,"
            "owner_team_id,"
            "metadata_json,bm_edges_json AS edges_json,unknown_json,resource_count,row_hash "
            "FROM orbit_meta_raw_account FORCE INDEX(PRIMARY) WHERE tenant_id=:tenant "
            "AND registry_id=:registry ORDER BY account_id LIMIT 501 FOR SHARE",
            base,
        )
        if len(actual_accounts) != len(prepared.accounts):
            invalid()
        size = 65536
        for actual, expected in zip(actual_accounts, prepared.accounts, strict=True):
            try:
                values = dict(actual)
                for key in ("metadata_json", "edges_json", "unknown_json"):
                    values[key] = canonical(json_value(values[key]))
                recorded_hash = values.pop("row_hash")
                if values != {
                    key: value for key, value in expected.__dict__.items() if key != "row_hash"
                }:
                    invalid()
                if digest(values) != recorded_hash or recorded_hash != expected.row_hash:
                    invalid()
                size += len(canonical(base | values | {"row_hash": recorded_hash}).encode())
            except (KeyError, TypeError, ValueError, UnicodeError):
                invalid()
        offset, after = 0, ("", "", "")
        while True:
            page = await rows(
                session,
                "SELECT account_id,kind,external_id,name,row_hash FROM orbit_meta_raw_resource "
                "FORCE INDEX(PRIMARY) WHERE tenant_id=:tenant AND registry_id=:registry "
                "AND (account_id,kind,external_id)>(:after_account,:after_kind,:after_external) "
                "ORDER BY account_id,kind,external_id LIMIT 200 FOR SHARE",
                base
                | {"after_account": after[0], "after_kind": after[1], "after_external": after[2]},
            )
            for actual in page:
                if offset >= len(prepared.resources):
                    invalid()
                expected = prepared.resources[offset]
                try:
                    values = dict(actual)
                    recorded_hash = values.pop("row_hash")
                    if values != {
                        key: value for key, value in expected.__dict__.items() if key != "row_hash"
                    }:
                        invalid()
                    if digest(values) != recorded_hash or recorded_hash != expected.row_hash:
                        invalid()
                    key = (values["account_id"], values["kind"], values["external_id"])
                    if key <= after:
                        invalid()
                    after = key
                    size += len(canonical(base | values | {"row_hash": recorded_hash}).encode())
                except (KeyError, TypeError, ValueError, UnicodeError):
                    invalid()
                offset += 1
                if size > MAX_BYTES:
                    invalid()
            if len(page) < 200:
                break
        if offset != len(prepared.resources) or size != prepared.stored_bytes:
            invalid()

    @staticmethod
    def receipt(prepared, identifier):
        return {
            "registry_id": identifier,
            "binding_sha256": prepared.bound.binding_sha256,
            "observed_at": prepared.bound.observation.observed_at.isoformat().replace(
                "+00:00", "Z"
            ),
            "account_count": len(prepared.accounts),
            "resource_count": len(prepared.resources),
            "execution_authorized": False,
        }

    async def register(self, session, actor, prepared, *, key, request_id):
        if not session.in_transaction():
            raise ValueError("原始观察登记需要调用方外层事务")
        if not isinstance(prepared, PreparedMetaObservation) or prepared._issuer is not _ISSUER:
            invalid()
        # 不信任替换过的小行/expected根，再次纯重算；无网络和数据库写。
        if self.prepare(prepared.bound) != prepared:
            invalid()
        if not isinstance(key, str) or re.fullmatch(r"[ -~]{16,128}", key) is None:
            raise OrbitError(400, "IDEMPOTENCY_REQUIRED", "需要固定原始观察幂等键")
        uuid_value(request_id)
        current = await require_business_access(session, actor, "accounts", "accounts.sync")
        source = prepared.bound.source
        if current.actor_id != source.actor_id or current.tenant_id != source.tenant_id:
            raise OrbitError(403, "PERMISSION_DENIED", "原始观察主体或租户不一致")
        params = parameters(current) | {
            "key": hashlib.sha256(key.encode()).hexdigest(),
            "op": OPERATION,
        }
        # 普通探测不先锁ledger再等账户；后面的所有范围都使用当前显式锁读。
        old = await one(
            session,
            "SELECT intent_hash,registry_id,receipt_json FROM orbit_meta_raw_idempotency "
            "WHERE tenant_id=:tenant AND actor_id=:actor AND operation=:op AND key_hash=:key",
            params,
        )
        if old:
            return await self.replay(session, current, old, prepared)
        configurations = await rows(
            session,
            "SELECT id,revision,settings_json,secrets_json "
            "FROM orbit_system_configuration FORCE INDEX(PRIMARY) "
            "WHERE tenant_id=:tenant AND section='META_BM' AND enabled=1 "
            "AND verification_status='READ_VERIFIED' ORDER BY id LIMIT 2 FOR SHARE",
            params,
        )
        watermark = await clock(session, current)
        current_rows = await self.visible_accounts(
            session, current, [row.account_id for row in prepared.accounts]
        )
        # 先完整upsert预留，再锁必然存在的key；不对missing key做locking read。
        identifier = str(uuid4())
        receipt = self.receipt(prepared, identifier)
        values = params | {
            "registry": identifier,
            "intent": prepared.intent_hash,
            "receipt": canonical(receipt),
        }
        # 完整预留同key；无NULL/BUILDING中间行。该表不对head建前向FK，防插入循环。
        await session.execute(
            text(
                "INSERT INTO orbit_meta_raw_idempotency(tenant_id,actor_id,operation,key_hash,"
                "intent_hash,registry_id,receipt_json,created_at) VALUES(:tenant,:actor,:op,:key,"
                ":intent,:registry,:receipt,UTC_TIMESTAMP(6)) ON DUPLICATE KEY UPDATE "
                "key_hash=key_hash"
            ),
            values,
        )
        reserved = await one(
            session,
            "SELECT intent_hash,registry_id,receipt_json FROM orbit_meta_raw_idempotency "
            "WHERE tenant_id=:tenant AND actor_id=:actor AND operation=:op AND key_hash=:key "
            "FOR UPDATE",
            params,
        )
        if reserved is None:
            invalid()
        if reserved["registry_id"] != identifier:
            return await self.replay(session, current, reserved, prepared)
        if len(configurations) != 1:
            stale()
        config = configurations[0]
        settings, secrets = json_value(config["settings_json"]), json_value(config["secrets_json"])
        if (
            not isinstance(settings, dict)
            or not isinstance(secrets, dict)
            or not secrets.get("accessToken")
            or config["id"] != source.configuration.source_config_id
            or config["revision"] != source.configuration.source_config_revision
            or settings.get("businessId") != source.configuration.business_id
            or settings.get("graphVersion") != source.configuration.api_version
        ):
            stale()
        version = (
            await session.execute(
                text(
                    "SELECT auth_version FROM sys_identity_subject WHERE user_id=:actor FOR SHARE"
                ),
                {"actor": actor},
            )
        ).scalar_one_or_none()
        if (
            watermark != source.account_clock
            or version != source.auth_version
            or (current.subject_id, current.team_id, current.data_role)
            != (source.subject_id, source.team_id, source.data_role)
        ):
            stale()
        for captured, actual in zip(prepared.accounts, current_rows, strict=True):
            if (
                actual["id"] != captured.account_id
                or actual["revision"] != captured.revision
                or actual["external_id"] != captured.external_id
                or actual["owner_user_id"] != captured.owner_user_id
                or actual["owner_team_id"] != captured.owner_team_id
                or actual["unbound_at"] is not None
            ):
                stale()
        now = (await session.execute(text("SELECT UTC_TIMESTAMP(6)"))).scalar_one()
        if database_time(now) < prepared.bound.observation.observed_at:
            stale()
        await self.write(session, current, prepared, identifier, request_id, values)
        return receipt

    async def write(self, session, current, prepared, identifier, request_id, values):
        source, observed = prepared.bound.source, prepared.bound.observation
        head = values | {
            "subject": source.subject_id,
            "auth": source.auth_version,
            "clock": source.account_clock,
            "config": observed.source_config_id,
            "config_revision": observed.source_config_revision,
            "business": observed.business_id,
            "version": observed.api_version,
            "captured": source.captured_at.replace(tzinfo=None),
            "started": observed.started_at.replace(tzinfo=None),
            "observed": observed.observed_at.replace(tzinfo=None),
            "source_hash": source.binding_sha256,
            "observation_hash": observed.evidence_sha256,
            "bound_hash": prepared.bound.binding_sha256,
            "accounts": len(prepared.accounts),
            "resources": len(prepared.resources),
            "requests": observed.request_count,
            "bytes": observed.response_bytes,
            "stored_bytes": prepared.stored_bytes,
        }
        await session.execute(
            text(
                "INSERT INTO orbit_meta_raw_head(tenant_id,id,actor_id,subject_id,auth_version,"
                "account_clock,"
                "source_config_id,source_config_revision,business_id,graph_version,captured_at,"
                "started_at,"
                "observed_at,source_binding_sha256,observation_sha256,bound_sha256,intent_hash,"
                "account_count,"
                "resource_count,request_count,response_bytes,stored_bytes) VALUES(:tenant,"
                ":registry,:actor,"
                ":subject,:auth,:clock,:config,:config_revision,:business,:version,:captured,"
                ":started,:observed,"
                ":source_hash,:observation_hash,:bound_hash,:intent,:accounts,:resources,"
                ":requests,:bytes,:stored_bytes)"
            ),
            head,
        )
        base = {"tenant": current.tenant_id, "registry": identifier}
        account_rows = (base | row.__dict__ for row in prepared.accounts)
        for batch in row_batches(account_rows):
            await session.execute(
                text(
                    "INSERT INTO orbit_meta_raw_account(tenant_id,registry_id,account_id,"
                    "account_revision,"
                    "external_id,owner_user_id,owner_team_id,metadata_json,bm_edges_json,"
                    "unknown_json,"
                    "resource_count,row_hash) VALUES(:tenant,:registry,:account_id,:revision,"
                    ":external_id,"
                    ":owner_user_id,:owner_team_id,:metadata_json,:edges_json,:unknown_json,"
                    ":resource_count,:row_hash)"
                ),
                batch,
            )
        for batch in row_batches(base | row.__dict__ for row in prepared.resources):
            await session.execute(
                text(
                    "INSERT INTO orbit_meta_raw_resource(tenant_id,registry_id,account_id,kind,"
                    "external_id,"
                    "name,row_hash) VALUES(:tenant,:registry,:account_id,:kind,:external_id,"
                    ":name,:row_hash)"
                ),
                batch,
            )
        audit = base | {
            "id": str(uuid4()),
            "actor": current.actor_id,
            "request": request_id,
            "details": canonical(self.receipt(prepared, identifier)),
        }
        if (
            len(
                canonical(
                    {
                        key: value.isoformat() if isinstance(value, datetime) else value
                        for key, value in head.items()
                    }
                ).encode()
            )
            + len(canonical(audit).encode())
            + len(canonical(values).encode())
            > 65536
        ):
            invalid()
        await session.execute(
            text(
                "INSERT INTO orbit_meta_raw_audit(tenant_id,id,registry_id,actor_id,request_id,"
                "details_json) "
                "VALUES(:tenant,:id,:registry,:actor,:request,:details)"
            ),
            audit,
        )
        await session.execute(
            text(
                "INSERT INTO orbit_meta_raw_outbox(tenant_id,event_id,state) VALUES(:tenant,"
                ":id,'PENDING')"
            ),
            audit,
        )
