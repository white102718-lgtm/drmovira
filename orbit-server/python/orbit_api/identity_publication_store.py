"""C1身份完整库存发布；原始观察/主体匹配不是能力发行，也不是平台写授权。

调用方负责外层事务与commit，返回metadata不能提前宣称已经持久化。
Authority网络capture只在prepare中执行；register仅允许当前数据库来源复核。
"""

import hashlib
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from sqlalchemy import text

from orbit_api import meta_identity_principal_binding as principal
from orbit_api.account_access import clock, event, parameters
from orbit_api.account_details_contract import iso
from orbit_api.account_identities_contract import identities
from orbit_api.account_identities_store import fingerprint
from orbit_api.authorization import require_business_access
from orbit_api.configuration_store import _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.meta_observation_registry import (
    MetaObservationRegistry,
    database_time,
    digest,
    instant,
    json_value,
    number,
    one,
    rows,
    uuid_value,
)
from orbit_api.reference_access import managed_teams

PROJECTION = "UTC_FLOOR_MS_V1"
_ISSUER = object()


def unavailable(code="IDENTITY_PUBLICATION_AUTHORITY_UNAVAILABLE"):
    raise OrbitError(503, code, "身份库存或独立能力发行证据尚未就绪") from None


def changed():
    raise OrbitError(409, "IDENTITY_PUBLICATION_SOURCE_CHANGED", "账户或身份来源已变化，请重新核验")


def floor_ms(value):
    """显式向下投影；绝不让DATETIME(3)隐式舍入改变原始证据。"""
    instant(value)
    return value.replace(microsecond=value.microsecond // 1000 * 1000)


@dataclass(frozen=True)
class IdentityDecision:
    kind: str
    external_id: str
    usable: bool
    reason_code: str | None


@dataclass(frozen=True, repr=False)
class IdentityQualification:
    """独立Authority结果，必须再与受控发行行和完整raw库存逐项绑定。"""

    release_id: str
    release_revision: int
    release_source_hash: str
    capability_version: str
    raw_bound_hash: str
    principal_hash: str
    account_id: str
    decisions: tuple[IdentityDecision, ...]
    observed_at: datetime
    credential_expires_at: datetime | None = None


class IdentityCapabilityAuthority(ABC):
    kind: str

    @abstractmethod
    async def capture(self, match, account_id) -> IdentityQualification:
        """数据库事务外捕获完整资格；不接受HTTP自由verified字段。"""

    @abstractmethod
    async def revalidate(self, session, current, prepared):
        """只锁数据库来源，必须在clock/account锁之前；不得执行网络。"""


@dataclass(frozen=True, repr=False)
class PreparedIdentityPublication:
    match: principal.BoundPrincipalMatch = field(repr=False)
    raw: object = field(repr=False)
    qualification: IdentityQualification = field(repr=False)
    registry_id: str
    expected_revision: int
    payload_json: str
    intent_hash: str
    authority: IdentityCapabilityAuthority = field(repr=False, compare=False)
    _issuer: object = field(repr=False, compare=False)


def check_match(match):
    if (
        not isinstance(match, principal.BoundPrincipalMatch)
        or match._issuer is not principal._ISSUER
    ):
        unavailable()
    principal.check_source(match.source)
    facts = match.facts
    # 原collector没有公开验证函数；按其固定schema重算完整事实正文，不信任保留hash。
    try:
        facts_hash = digest(
            {
                "schema_version": 1,
                "source_binding_sha256": facts.source_binding_sha256,
                "source_config_id": facts.source_config_id,
                "source_config_revision": facts.source_config_revision,
                "business_id": facts.business_id,
                "api_version": facts.api_version,
                "started_at": facts.started_at.isoformat(),
                "observed_at": facts.observed_at.isoformat(),
                "principal_id": facts.principal_id,
                "principal_reason": facts.principal_reason,
                "principal_binding": "CONFIG_PRINCIPAL_NOT_BOUND",
                "resources": [
                    dict(
                        account_id=r.account_id,
                        kind=r.kind,
                        external_id=r.external_id,
                        object_facts=json.loads(r.object_facts_json)
                        if r.object_facts_json
                        else None,
                        assignments=json.loads(r.assignment_facts_json)
                        if r.assignment_facts_json
                        else None,
                        object_reason=r.object_reason,
                        assignment_reason=r.assignment_reason,
                        unknown_fields=r.unknown_fields,
                    )
                    for r in facts.resources
                ],
            }
        )
    except (TypeError, ValueError, AttributeError, UnicodeError):
        unavailable()
    if (
        facts.evidence_sha256 != facts_hash
        or facts.source_binding_sha256 != match.source.bound.binding_sha256
        or facts.principal_id != match.principal_id
        or match.principal_id != match.source.system_user_id
        or match.evidence_sha256
        != digest(
            {
                "schema_version": 1,
                "source_sha256": match.source.source_sha256,
                "facts_sha256": facts.evidence_sha256,
                "principal_id": match.principal_id,
                "principal_matches": True,
            }
        )
    ):
        unavailable()


def publication_payload(match, qualification):
    """资格必须覆盖该账户完整库存；M3所选资源集合不当作完整库存。"""
    check_match(match)
    if not isinstance(qualification, IdentityQualification):
        unavailable()
    q = qualification
    uuid_value(q.account_id)
    uuid_value(q.release_id)
    number(q.release_revision)
    if not isinstance(q.release_source_hash, str) or not re.fullmatch(
        "[0-9a-f]{64}", q.release_source_hash
    ):
        unavailable()
    raw = MetaObservationRegistry().prepare(match.source.bound)
    if q.account_id not in {row.account_id for row in raw.accounts}:
        unavailable()
    if (q.raw_bound_hash, q.principal_hash) != (raw.bound.binding_sha256, match.evidence_sha256):
        unavailable()
    instant(q.observed_at)
    if q.observed_at < max(raw.bound.observation.observed_at, match.facts.observed_at):
        unavailable()
    if q.credential_expires_at is not None:
        instant(q.credential_expires_at)
        if q.credential_expires_at <= q.observed_at:
            unavailable()
    inventory = {(r.kind, r.external_id): r for r in raw.resources if r.account_id == q.account_id}
    if (
        type(q.decisions) is not tuple
        or len(q.decisions) != len(inventory)
        or len(inventory) > 5000
    ):
        unavailable("IDENTITY_PUBLICATION_INVENTORY_INCOMPLETE")
    resources, used = [], set()
    for decision in q.decisions:
        if not isinstance(decision, IdentityDecision):
            unavailable()
        key = (decision.kind, decision.external_id)
        if key not in inventory or key in used or type(decision.usable) is not bool:
            unavailable("IDENTITY_PUBLICATION_INVENTORY_INCOMPLETE")
        used.add(key)
        # NULL/超长原名不裁剪，不用ID伪造名称；原023合同要求字符串<=255。
        name = inventory[key].name
        if not isinstance(name, str) or len(name) > 255:
            unavailable("IDENTITY_PUBLICATION_NAME_UNREPRESENTABLE")
        resources.append(
            {
                "kind": decision.kind,
                "external_id": decision.external_id,
                "name": name,
                "usable": decision.usable,
                "reason_code": decision.reason_code,
            }
        )
    try:
        value = identities(
            {
                "account_id": q.account_id,
                "resources": resources,
                "capability_version": q.capability_version,
                "observed_at": iso(floor_ms(q.observed_at)),
            },
            expected_account_id=q.account_id,
        )
    except OrbitError:
        unavailable("IDENTITY_PUBLICATION_INVENTORY_INVALID")
    value["resources"].sort(key=lambda r: (r["kind"], r["external_id"]))
    return raw, value


def intent_document(match, q, registry_id, expected_revision, value):
    return {
        "schema_version": 1,
        "projection_version": PROJECTION,
        "registry_id": registry_id,
        "bound_sha256": q.raw_bound_hash,
        "principal_sha256": q.principal_hash,
        "facts_sha256": match.facts.evidence_sha256,
        "release_id": q.release_id,
        "release_revision": q.release_revision,
        "release_source_hash": q.release_source_hash,
        "expected_revision": expected_revision,
        "payload": value,
        "raw_observed_at": q.observed_at.isoformat(),
        "credential_expires_at": q.credential_expires_at.isoformat()
        if q.credential_expires_at
        else None,
    }


async def authority_database(session, kind):
    if kind == "TRUSTED":
        return
    if kind != "ISOLATED_TEST":
        unavailable()
    bind = session.get_bind()
    # 独占RC会话绑定真实Connection，普通框架会话绑定Engine；两者仍核同一数据库。
    url = getattr(bind, "url", None)
    if url is None:
        url = bind.engine.url
    if (
        url.host not in {"127.0.0.1", "localhost"}
        or url.port != 13306
        or not re.fullmatch(r"orbit_py_it_[0-9a-f]{32}", url.database or "")
    ):
        unavailable()
    if (await session.execute(text("SELECT DATABASE()"))).scalar_one() != url.database:
        unavailable()


async def current_accounts(session, current, identifiers, *, write=False):
    managed = set(await managed_teams(session, current))
    result = []
    for offset in range(0, len(identifiers), 200):
        page = await rows(
            session,
            "SELECT id,revision,external_id,owner_user_id,owner_team_id,"
            "auth_status,account_status,unbound_at FROM orbit_ad_account "
            "FORCE INDEX(PRIMARY) WHERE tenant_id=:tenant AND id IN :ids ORDER BY id "
            + ("FOR UPDATE" if write else "FOR SHARE"),
            {"tenant": current.tenant_id},
            ids=identifiers[offset : offset + 200],
        )
        if {r["id"] for r in page} != set(identifiers[offset : offset + 200]):
            raise OrbitError(404, "NOT_FOUND", "账户不存在或不在当前数据范围")
        for row in page:
            if (
                current.data_role != "SUPER_ADMIN"
                and row["owner_user_id"] != current.subject_id
                and not (current.data_role == "TEAM_ADMIN" and row["owner_team_id"] in managed)
            ):
                raise OrbitError(404, "NOT_FOUND", "账户不存在或不在当前数据范围")
        result.extend(page)
    return result


async def lock_sources(session, current, release_id):
    # 全配置按UUID当前锁读；release独立来源随后锁，均先于账户clock。
    configurations = await rows(
        session,
        "SELECT id,revision,settings_json,secrets_json FROM "
        "orbit_system_configuration FORCE INDEX(PRIMARY) WHERE tenant_id=:tenant "
        "AND section='META_BM' AND enabled=1 AND verification_status='READ_VERIFIED' "
        "ORDER BY id FOR SHARE",
        {"tenant": current.tenant_id},
    )
    release = await one(
        session,
        "SELECT * FROM orbit_identity_capability_release WHERE "
        "tenant_id=:tenant AND id=:release FOR SHARE",
        {"tenant": current.tenant_id, "release": release_id},
    )
    return configurations, release


def valid_release(release, configuration, *, kind, version, revision, source_hash, business, graph):
    if release is None or (
        release["revoked_at"] is not None
        or release["revision"] != revision
        or release["capability_version"] != version
        or release["source_hash"] != source_hash
        or release["source_config_id"] != configuration["id"]
        or release["source_config_revision"] != configuration["revision"]
        or release["business_id"] != business
        or release["graph_version"] != graph
        or release["action_scope"] != "ACCOUNT_IDENTITIES_READ"
        or not release["issuer"]
        or release["source_kind"]
        != ("ISOLATED_PROTOCOL" if kind == "ISOLATED_TEST" else "META_AUTHORITY")
    ):
        unavailable("IDENTITY_PUBLICATION_RELEASE_UNAVAILABLE")


class IdentityPublicationStore:
    def __init__(self, authority=None):
        self.authority = authority

    async def successful_replay(self, session, actor, *, key, intent_hash):
        """重启后先恢复原metadata，无需重新网络捕获或仍有Authority。

        调用方必须保留原完整意图根；此方法不授资源读取/发布资格，也不返回旧resources。
        missing key不锁gap；命中后先当前动作/全部原账户范围，才比旧意图。
        """
        if not session.in_transaction():
            raise ValueError("历史发布回执读取需要调用方显式外层事务")
        if not isinstance(key, str) or re.fullmatch(r"[ -~]{16,128}", key) is None:
            raise OrbitError(400, "IDEMPOTENCY_REQUIRED", "需要固定身份发布幂等键")
        if not isinstance(intent_hash, str) or re.fullmatch("[0-9a-f]{64}", intent_hash) is None:
            unavailable()
        current = await require_business_access(session, actor, "accounts", "accounts.sync")
        p = parameters(current) | {"key": hashlib.sha256(key.encode()).hexdigest()}
        old = await one(
            session,
            "SELECT intent_hash,evidence_id,receipt_json FROM "
            "orbit_identity_publication_ledger WHERE tenant_id=:tenant "
            "AND actor_id=:actor AND key_hash=:key",
            p,
        )
        if old is None:
            return None
        # 只发现不变raw登记ID；在当前clock和账户范围后才读取/返回历史metadata。
        probe = await one(
            session,
            "SELECT registry_id FROM orbit_identity_publication_provenance "
            "WHERE tenant_id=:tenant AND evidence_id=:evidence",
            p | {"evidence": old["evidence_id"]},
        )
        if probe is None:
            unavailable("IDENTITY_PUBLICATION_HISTORY_INVALID")
        await clock(session, current)
        accounts = await rows(
            session,
            "SELECT account_id FROM orbit_meta_raw_account WHERE "
            "tenant_id=:tenant AND registry_id=:registry ORDER BY account_id "
            "LIMIT 501 FOR SHARE",
            p | {"registry": probe["registry_id"]},
        )
        if not 1 <= len(accounts) <= 500:
            unavailable("IDENTITY_PUBLICATION_HISTORY_INVALID")
        await current_accounts(session, current, [r["account_id"] for r in accounts])
        if old["intent_hash"] != intent_hash:
            raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "同一幂等键不得改变身份发布正文")
        proof = await one(
            session,
            "SELECT * FROM orbit_identity_publication_provenance WHERE "
            "tenant_id=:tenant AND evidence_id=:evidence FOR SHARE",
            p | {"evidence": old["evidence_id"]},
        )
        if (
            proof is None
            or proof["intent_hash"] != intent_hash
            or proof["registry_id"] != probe["registry_id"]
        ):
            unavailable("IDENTITY_PUBLICATION_HISTORY_INVALID")
        value = await verify_history(session, current, proof)
        expected = {
            "account_id": proof["account_id"],
            "evidence_id": proof["evidence_id"],
            "revision": proof["identity_revision"],
            "payload_hash": proof["payload_hash"],
            "observed_at": value["observed_at"],
            "execution_authorized": False,
        }
        if json_value(old["receipt_json"]) != expected:
            unavailable("IDENTITY_PUBLICATION_HISTORY_INVALID")
        return expected

    async def prepare(self, match, account_id, *, registry_id, expected_revision):
        if not isinstance(self.authority, IdentityCapabilityAuthority):
            unavailable()
        check_match(match)
        uuid_value(registry_id)
        number(expected_revision, minimum=0)
        q = await self.authority.capture(match, account_id)
        if not isinstance(q, IdentityQualification) or q.account_id != account_id:
            unavailable()
        raw, value = publication_payload(match, q)
        intent = digest(intent_document(match, q, registry_id, expected_revision, value))
        return PreparedIdentityPublication(
            match,
            raw,
            q,
            registry_id,
            expected_revision,
            canonical(value),
            intent,
            self.authority,
            _ISSUER,
        )

    @staticmethod
    def check(prepared):
        if not isinstance(prepared, PreparedIdentityPublication) or prepared._issuer is not _ISSUER:
            unavailable()
        raw, value = publication_payload(prepared.match, prepared.qualification)
        if (
            raw != prepared.raw
            or canonical(value) != prepared.payload_json
            or digest(
                intent_document(
                    prepared.match,
                    prepared.qualification,
                    prepared.registry_id,
                    prepared.expected_revision,
                    value,
                )
            )
            != prepared.intent_hash
        ):
            unavailable()
        return value

    async def replay(self, session, current, ledger, prepared):
        await clock(session, current)
        await current_accounts(session, current, [r.account_id for r in prepared.raw.accounts])
        if ledger["intent_hash"] != prepared.intent_hash:
            raise OrbitError(409, "IDEMPOTENCY_CONFLICT", "同一幂等键不得改变身份发布正文")
        proof = await one(
            session,
            "SELECT * FROM orbit_identity_publication_provenance "
            "WHERE tenant_id=:tenant AND evidence_id=:evidence FOR SHARE",
            {"tenant": current.tenant_id, "evidence": ledger["evidence_id"]},
        )
        receipt = json_value(ledger["receipt_json"])
        if (
            proof is None
            or proof["intent_hash"] != prepared.intent_hash
            or receipt != self.receipt(prepared, ledger["evidence_id"], proof["identity_revision"])
        ):
            unavailable("IDENTITY_PUBLICATION_HISTORY_INVALID")
        # 历史回执不返回旧资源；仍验证原完整版本，不能只相信旁证头。
        await verify_history(session, current, proof, prepared.payload_json)
        return receipt

    @staticmethod
    def receipt(prepared, evidence_id, revision):
        return {
            "account_id": prepared.qualification.account_id,
            "evidence_id": evidence_id,
            "revision": revision,
            "payload_hash": fingerprint(json_value(prepared.payload_json)),
            "observed_at": iso(floor_ms(prepared.qualification.observed_at)),
            "execution_authorized": False,
        }

    async def register(self, session, actor, prepared, *, key, request_id):
        if not session.in_transaction():
            raise ValueError("身份发布需要调用方显式外层事务")
        value = self.check(prepared)
        uuid_value(request_id)
        if not isinstance(key, str) or re.fullmatch(r"[ -~]{16,128}", key) is None:
            raise OrbitError(400, "IDEMPOTENCY_REQUIRED", "需要固定身份发布幂等键")
        current = await require_business_access(session, actor, "accounts", "accounts.sync")
        source, q = prepared.raw.bound.source, prepared.qualification
        if current.tenant_id != source.tenant_id or current.actor_id != source.actor_id:
            raise OrbitError(403, "PERMISSION_DENIED", "身份发布主体或租户不一致")
        p = parameters(current) | {"key": hashlib.sha256(key.encode()).hexdigest()}
        old = await one(
            session,
            "SELECT intent_hash,evidence_id,receipt_json FROM "
            "orbit_identity_publication_ledger WHERE tenant_id=:tenant "
            "AND actor_id=:actor AND key_hash=:key",
            p,
        )
        if old:
            return await self.replay(session, current, old, prepared)
        await authority_database(session, prepared.authority.kind)
        configurations, release = await lock_sources(session, current, q.release_id)
        # 锁在来源阶段取得，版本失效延至确认本次reserve获胜后拒绝；不抢在并发成功重放之前。
        authority_failure = None
        try:
            await prepared.authority.revalidate(session, current, prepared)
        except OrbitError as error:
            if error.status not in (409, 503):
                raise
            authority_failure = error
        watermark = await clock(session, current, write=True)
        actual = await current_accounts(
            session, current, [r.account_id for r in prepared.raw.accounts], write=True
        )
        evidence_id = str(uuid4())
        receipt = self.receipt(prepared, evidence_id, prepared.expected_revision + 1)
        p |= {
            "evidence": evidence_id,
            "intent": prepared.intent_hash,
            "receipt": canonical(receipt),
        }
        await session.execute(
            text(
                "INSERT INTO orbit_identity_publication_ledger"
                "(tenant_id,actor_id,key_hash,intent_hash,evidence_id,receipt_json) "
                "VALUES(:tenant,:actor,:key,:intent,:evidence,:receipt) "
                "ON DUPLICATE KEY UPDATE key_hash=key_hash"
            ),
            p,
        )
        reserved = await one(
            session,
            "SELECT intent_hash,evidence_id,receipt_json FROM "
            "orbit_identity_publication_ledger WHERE tenant_id=:tenant "
            "AND actor_id=:actor AND key_hash=:key FOR UPDATE",
            p,
        )
        if reserved is None:
            unavailable()
        if reserved["evidence_id"] != evidence_id:
            return await self.replay(session, current, reserved, prepared)
        if authority_failure is not None:
            raise authority_failure
        if len(configurations) != 1:
            changed()
        config = configurations[0]
        settings, secrets = _decode(config["settings_json"]), _decode(config["secrets_json"])
        c = source.configuration
        if (
            (config["id"], config["revision"]) != (c.source_config_id, c.source_config_revision)
            or (
                settings.get("businessId"),
                settings.get("graphVersion"),
                settings.get("systemUserId"),
            )
            != (c.business_id, c.api_version, prepared.match.principal_id)
            or not secrets.get("accessToken")
        ):
            changed()
        valid_release(
            release,
            config,
            kind=prepared.authority.kind,
            version=q.capability_version,
            revision=q.release_revision,
            source_hash=q.release_source_hash,
            business=c.business_id,
            graph=c.api_version,
        )
        auth = (
            await session.execute(
                text(
                    "SELECT auth_version FROM sys_identity_subject WHERE user_id=:actor FOR SHARE"
                ),
                {"actor": actor},
            )
        ).scalar_one_or_none()
        if (
            watermark != source.account_clock
            or auth != source.auth_version
            or (current.subject_id, current.team_id, current.data_role)
            != (source.subject_id, source.team_id, source.data_role)
        ):
            changed()
        for original, row in zip(prepared.raw.accounts, actual, strict=True):
            if (
                row["id"],
                row["revision"],
                row["external_id"],
                row["owner_user_id"],
                row["owner_team_id"],
            ) != (
                original.account_id,
                original.revision,
                original.external_id,
                original.owner_user_id,
                original.owner_team_id,
            ) or row["unbound_at"] is not None:
                changed()
        account = next(row for row in actual if row["id"] == q.account_id)
        if account["auth_status"] != "AUTHORIZED" or account["account_status"] != "ACTIVE":
            unavailable("ACCOUNT_IDENTITY_ACCOUNT_UNAVAILABLE")
        raw_head = await one(
            session,
            "SELECT bound_sha256,intent_hash FROM orbit_meta_raw_head "
            "WHERE tenant_id=:tenant AND id=:registry FOR SHARE",
            p | {"registry": prepared.registry_id},
        )
        if raw_head is None or (raw_head["bound_sha256"], raw_head["intent_hash"]) != (
            source_binding(prepared),
            prepared.raw.intent_hash,
        ):
            unavailable("IDENTITY_PUBLICATION_RAW_UNAVAILABLE")
        await MetaObservationRegistry().verify_details(
            session, current, prepared.registry_id, prepared.raw
        )
        now = database_time((await session.execute(text("SELECT UTC_TIMESTAMP(6)"))).scalar_one())
        if (
            q.observed_at > now
            or q.credential_expires_at is not None
            and q.credential_expires_at <= now
        ):
            unavailable("IDENTITY_PUBLICATION_OBSERVATION_STALE")
        previous = await one(
            session,
            "SELECT h.revision,h.observed_at FROM orbit_account_identity_head p "
            "JOIN orbit_account_identity_history h ON h.tenant_id=p.tenant_id "
            "AND h.account_id=p.account_id AND h.revision=p.revision "
            "WHERE p.tenant_id=:tenant AND p.account_id=:account FOR UPDATE OF p",
            p | {"account": q.account_id},
        )
        if (previous["revision"] if previous else 0) != prepared.expected_revision:
            raise OrbitError(409, "REVISION_CONFLICT", "身份库存版本已变化")
        if previous and floor_ms(q.observed_at) <= database_time(previous["observed_at"]):
            raise OrbitError(409, "OBSERVATION_STALE", "同毫秒或迟到观察不能覆盖完整库存")
        await self.write(session, current, prepared, value, p, request_id)
        return receipt

    async def write(self, session, current, prepared, value, p, request_id):
        q, source = prepared.qualification, prepared.raw.bound.source
        v = p | {
            "account": q.account_id,
            "revision": prepared.expected_revision + 1,
            "account_revision": next(
                r.revision for r in prepared.raw.accounts if r.account_id == q.account_id
            ),
            "config": source.configuration.source_config_id,
            "config_revision": source.configuration.source_config_revision,
            "version": q.capability_version,
            "payload": fingerprint(value),
            "observed": floor_ms(q.observed_at).replace(tzinfo=None),
            "expires": floor_ms(q.credential_expires_at).replace(tzinfo=None)
            if q.credential_expires_at
            else None,
            "ref": "PUBLICATION_V1:" + p["evidence"],
            "request": request_id,
            "count": len(value["resources"]),
        }
        await session.execute(
            text(
                "INSERT INTO "
                "orbit_account_identity_evidence(tenant_id,id,account_id,account_revision,"
                "source_config_id,source_config_revision,capability_version,payload_hash,observed_at,"
                "complete,verified,credential_expires_at,evidence_ref,created_at) "
                "VALUES(:tenant,:evidence,:account,"
                ":account_revision,:config,:config_revision,:version,:payload,:observed,1,1,:expires,:ref,UTC_TIMESTAMP(3))"
            ),
            v,
        )
        await session.execute(
            text(
                "INSERT INTO "
                "orbit_account_identity_history(tenant_id,account_id,revision,evidence_id,"
                "capability_version,observed_at,resource_count,request_id,created_at) "
                "VALUES(:tenant,:account,:revision,"
                ":evidence,:version,:observed,:count,:request,UTC_TIMESTAMP(3))"
            ),
            v,
        )
        for start in range(0, len(value["resources"]), 100):
            await session.execute(
                text(
                    "INSERT INTO "
                    "orbit_account_identity_resource(tenant_id,account_id,revision,kind,"
                    "external_id,name,usable,reason_code) VALUES(:tenant,:account,:revision,:kind,"
                    ":external_id,:name,:usable,:reason_code)"
                ),
                [v | item for item in value["resources"][start : start + 100]],
            )
        await session.execute(
            text(
                "INSERT INTO orbit_account_identity_head(tenant_id,account_id,revision) "
                "VALUES(:tenant,:account,:revision) ON DUPLICATE KEY UPDATE revision=:revision"
            ),
            v,
        )
        proof = v | {
            "registry": prepared.registry_id,
            "release": q.release_id,
            "release_revision": q.release_revision,
            "release_hash": q.release_source_hash,
            "raw_observed": q.observed_at.replace(tzinfo=None),
            "raw_expires": q.credential_expires_at.replace(tzinfo=None)
            if q.credential_expires_at
            else None,
            "bound": source_binding(prepared),
            "principal": q.principal_hash,
            "facts": prepared.match.facts.evidence_sha256,
            "projection": PROJECTION,
            "principal_id": prepared.match.principal_id,
            "authority_kind": prepared.authority.kind,
        }
        await session.execute(
            text(
                "INSERT INTO "
                "orbit_identity_publication_provenance(tenant_id,evidence_id,account_id,"
                "identity_revision,registry_id,release_id,release_revision,release_source_hash,"
                "raw_observed_at,raw_credential_expires_at,bound_sha256,principal_sha256,facts_sha256,"
                "principal_id,projection_version,payload_hash,intent_hash,authority_kind) "
                "VALUES(:tenant,:evidence,"
                ":account,:revision,:registry,:release,:release_revision,:release_hash,:raw_observed,"
                ":raw_expires,:bound,:principal,:facts,:principal_id,:projection,:payload,:intent,:authority_kind)"
            ),
            proof,
        )
        await event(
            session,
            current,
            "IDENTITIES",
            q.account_id,
            v["revision"],
            "ACCOUNT_IDENTITIES_PUBLISHED",
            request_id,
            {
                "evidence_id": p["evidence"],
                "resource_count": v["count"],
                "registry_id": prepared.registry_id,
                "projection_version": PROJECTION,
            },
        )


def source_binding(prepared):
    return prepared.raw.bound.binding_sha256


async def verify_history(session, current, proof, expected_json=None):
    p = {
        "tenant": current.tenant_id,
        "account": proof["account_id"],
        "revision": proof["identity_revision"],
    }
    head = await one(
        session,
        "SELECT * FROM orbit_account_identity_history WHERE tenant_id=:tenant "
        "AND account_id=:account AND revision=:revision FOR SHARE",
        p,
    )
    resources = await rows(
        session,
        "SELECT kind,external_id,name,usable,reason_code FROM "
        "orbit_account_identity_resource WHERE tenant_id=:tenant AND account_id=:account "
        "AND revision=:revision ORDER BY kind,external_id LIMIT 5001 FOR SHARE",
        p,
    )
    if (
        head is None
        or head["evidence_id"] != proof["evidence_id"]
        or len(resources) != head["resource_count"]
        or len(resources) > 5000
    ):
        unavailable("IDENTITY_PUBLICATION_HISTORY_INVALID")
    if any(type(r["usable"]) not in (int, bool) or r["usable"] not in (0, 1) for r in resources):
        unavailable("IDENTITY_PUBLICATION_HISTORY_INVALID")
    value = {
        "account_id": proof["account_id"],
        "resources": [dict(r) | {"usable": bool(r["usable"])} for r in resources],
        "capability_version": head["capability_version"],
        "observed_at": iso(database_time(head["observed_at"])),
    }
    try:
        value = identities(value, expected_account_id=proof["account_id"])
    except OrbitError:
        unavailable("IDENTITY_PUBLICATION_HISTORY_INVALID")
    if (
        fingerprint(value) != proof["payload_hash"]
        or expected_json is not None
        and canonical(value) != expected_json
    ):
        unavailable("IDENTITY_PUBLICATION_HISTORY_INVALID")
    return value
