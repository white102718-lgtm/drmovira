"""055有界身份摘要：MAC只证明本系统完整性，绝不发行Meta资格或执行权。

列表prepare必须在clock之前；resolve不补首次来源锁，不扫描resources。
完整资源hash仅seal_published后台入口核验。公共RC会话/details接线由主线负责。
"""

import hmac
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from weakref import WeakKeyDictionary

from sqlalchemy import text

from orbit_api.account_access import clock, context
from orbit_api.account_details_contract import iso
from orbit_api.account_identities_store import fingerprint
from orbit_api.authorization import require_business_access
from orbit_api.configuration_store import _decode
from orbit_api.cookie_identity import current_cookie_identity, ensure_cookie_current
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.identity_publication_store import (
    PROJECTION,
    IdentityPublicationStore,
    authority_database,
    current_accounts,
    floor_ms,
    valid_release,
    verify_history,
)
from orbit_api.meta_observation_registry import database_time, rows, uuid_value
from orbit_api.native_session import current_auth_snapshot

PURPOSE = "IDENTITY_SUMMARY_SEAL_V1"
_ISSUER = object()
_CANONICAL_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

# 只有严格白名单进入MAC；created_at不是业务来源，不依赖任意JSON或verified布尔。
CLAIM_FIELDS = (
    "tenant_id",
    "account_id",
    "revision",
    "evidence_id",
    "registry_id",
    "release_id",
    "release_revision",
    "release_source_hash",
    "source_config_id",
    "source_config_revision",
    "account_revision",
    "capability_version",
    "resource_count",
    "observed_at",
    "raw_observed_at",
    "raw_credential_expires_at",
    "bound_sha256",
    "principal_sha256",
    "facts_sha256",
    "principal_id",
    "projection_version",
    "payload_hash",
    "intent_hash",
    "authority_kind",
    "key_id",
)
UUID_FIELDS = {
    "tenant_id",
    "account_id",
    "evidence_id",
    "registry_id",
    "release_id",
    "source_config_id",
}
HASH_FIELDS = {
    "release_source_hash",
    "bound_sha256",
    "principal_sha256",
    "facts_sha256",
    "payload_hash",
    "intent_hash",
}
NUMBER_FIELDS = {"revision", "release_revision", "source_config_revision", "account_revision"}


def unknown(status="UNKNOWN"):
    return {"identity_status": status, "identity_count": None, "identity_observed_at": None}


def invalid():
    raise OrbitError(503, "IDENTITY_SUMMARY_INVALID", "身份摘要完整性或同事务票据不可用") from None


def transaction(session):
    sync = getattr(session, "sync_session", None)
    value = sync.get_transaction() if sync is not None else None
    if value is None:
        raise ValueError("身份摘要需要显式外层事务")
    return value


def identifiers(values):
    if not isinstance(values, (tuple, list)) or len(values) > 200:
        invalid()
    normalized = tuple(sorted(uuid_value(value) for value in values))
    if len(set(normalized)) != len(normalized):
        invalid()
    return normalized


def seal_claims(row):
    """DATETIME6使用明确六位精度；原023毫秒独立向下投影，不靠数据库舍入。"""
    try:
        value = {key: row[key] for key in CLAIM_FIELDS}
        for key in UUID_FIELDS:
            # 等价于原UUID解析后字符串完全相等；保留全部位值，不限制UUID版本。
            if not isinstance(value[key], str) or _CANONICAL_UUID.fullmatch(value[key]) is None:
                invalid()
        for key in HASH_FIELDS:
            if not isinstance(value[key], str) or re.fullmatch("[0-9a-f]{64}", value[key]) is None:
                invalid()
        for key in NUMBER_FIELDS:
            if type(value[key]) is not int or not 1 <= value[key] <= 9007199254740991:
                invalid()
        if type(value["resource_count"]) is not int or not 0 <= value["resource_count"] <= 5000:
            invalid()
        if (
            not isinstance(value["capability_version"], str)
            or not 1 <= len(value["capability_version"]) <= 64
        ):
            invalid()
        if not isinstance(value["principal_id"], str) or not re.fullmatch(
            r"[0-9]{1,64}", value["principal_id"]
        ):
            invalid()
        if value["projection_version"] != PROJECTION or value["authority_kind"] not in {
            "TRUSTED",
            "ISOLATED_TEST",
        }:
            invalid()
        if not isinstance(value["key_id"], str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,40}", value["key_id"]
        ):
            invalid()
        observed = database_time(value["observed_at"])
        raw = database_time(value["raw_observed_at"])
        if observed != floor_ms(raw):
            invalid()
        value["observed_at"] = iso(observed)
        value["raw_observed_at"] = raw.isoformat(timespec="microseconds").replace("+00:00", "Z")
        expiry = value["raw_credential_expires_at"]
        if expiry is not None:
            expiry = database_time(expiry)
            if expiry <= raw:
                invalid()
            value["raw_credential_expires_at"] = expiry.isoformat(timespec="microseconds").replace(
                "+00:00", "Z"
            )
        # 其他字符串已约束为ASCII或规范时间；只需检查自由文本的UTF-8可编码性。
        value["capability_version"].encode("utf-8")
        return {"schema_version": 1, **value}
    except (KeyError, TypeError, ValueError, UnicodeError):
        invalid()


def check_mac(cipher, row):
    try:
        return _check_mac_claims(cipher, row, seal_claims(row))
    except (OrbitError, KeyError, TypeError, ValueError, UnicodeError):
        return False


def _check_mac_claims(cipher, row, claims):
    """仅接收本模块刚校验的claims，避免一次读取重复解析同一签名载荷。"""
    if cipher is None:
        return False
    try:
        body = canonical(claims).encode("utf-8")
        signature = row["mac"]
        if not isinstance(signature, str) or re.fullmatch(r"[A-Za-z0-9_-]{43}", signature) is None:
            return False
        expected = cipher.application_mac(PURPOSE, body, row["key_id"])
        return hmac.compare_digest(expected, signature)
    except (OrbitError, KeyError, TypeError, ValueError, UnicodeError):
        # 未知/退役key只UNKNOWN，不能默用新active key验证或回填历史。
        return False


def matches_current_seal(cipher, expected, row):
    """完整校验封印，再逐字段核当前来源类型和值；相等字段继承同一有效约束。

    数值必须严格int，不让True==1通过；时间按原UTC规范比较。当前字段与已校验
    字段全等后，无需重复正则和序列化，不缓存当前权限或跳过任何MAC字段。
    """
    try:
        stored_claims = seal_claims(row)
        for key in CLAIM_FIELDS:
            current, sealed = expected[key], row[key]
            if key in {"observed_at", "raw_observed_at", "raw_credential_expires_at"}:
                if current is None or sealed is None:
                    if current is not None or sealed is not None:
                        return False
                elif database_time(current) != database_time(sealed):
                    return False
            elif key in NUMBER_FIELDS or key == "resource_count":
                if type(current) is not int or current != sealed:
                    return False
            elif not isinstance(current, str) or current != sealed:
                return False
        return _check_mac_claims(cipher, row, stored_claims)
    except (OrbitError, KeyError, TypeError, ValueError, UnicodeError):
        return False


@dataclass(frozen=True, repr=False)
class SummaryTicket:
    session: object = field(repr=False, compare=False)
    transaction: object = field(repr=False, compare=False)
    current: object = field(repr=False)
    permission: str
    candidates: tuple[str, ...]
    probes: object = field(repr=False)
    configurations: tuple = field(repr=False)
    releases: object = field(repr=False)
    _issuer: object = field(repr=False, compare=False)


@dataclass(frozen=True, eq=False, slots=True, weakref_slot=True, repr=False)
class _ListAuthorizationTicket:
    # 身份hash/弱引用均按对象本身；不按字段值等价，复制对象不能继承登记资格。
    session: object
    transaction: object
    actor: int
    permission: str
    current: object
    managed: tuple
    native_identity: object
    cookie_identity: object


class IdentityPublicationSummary:
    def __init__(self, cipher=None):
        self.cipher = cipher
        # 登记值不引用票据；弱键回收时同步释放登记的请求session和不可变期望值。
        self._list_authorizations = WeakKeyDictionary()

    @staticmethod
    def _list_transaction(session):
        tx = transaction(session)
        nested = getattr(session.sync_session, "get_nested_transaction", None)
        if not callable(nested) or nested() is not None:
            invalid()
        return tx

    async def authorize_list(self, session, actor):
        """替代列表已有的首次授权；不缓存其他请求，不改变普通prepare/sync。"""
        tx = self._list_transaction(session)
        current, managed = await context(session, actor, "accounts.read")
        if current.actor_id != actor or self._list_transaction(session) is not tx:
            invalid()
        ticket = _ListAuthorizationTicket(
            session,
            tx,
            actor,
            "accounts.read",
            current,
            tuple(managed),
            current_auth_snapshot(),
            current_cookie_identity(),
        )
        self._list_authorizations[ticket] = (
            session,
            tx,
            actor,
            "accounts.read",
            current,
            self._list_context_values(current),
            ticket.managed,
            ticket.native_identity,
            ticket.cookie_identity,
        )
        return current, managed, ticket

    @staticmethod
    def _list_context_values(current):
        # 保留primitive原值和类型，不因原context对象被强制修改而同步改变期望。
        return tuple(
            (type(value), value)
            for value in (
                current.actor_id,
                current.tenant_id,
                current.data_role,
                current.subject_id,
                current.team_id,
            )
        )

    async def _consume_list_authorization(self, session, actor, ticket):
        """仅固定只读列表路径消费首次已锁授权；到期Cookie仍按当前时刻重验。"""
        if type(ticket) is not _ListAuthorizationTicket:
            invalid()
        # 失败也消费，不能修补票据后再次尝试；不回退到普通鉴权绕过协议错误。
        registered = self._list_authorizations.pop(ticket, None)
        if registered is None:
            invalid()
        (
            original_session,
            original_tx,
            original_actor,
            original_permission,
            original_current,
            original_values,
            original_managed,
            original_native,
            original_cookie,
        ) = registered
        if (
            ticket.session is not original_session
            or ticket.transaction is not original_tx
            or type(ticket.actor) is not int
            or ticket.actor != original_actor
            or type(ticket.permission) is not str
            or ticket.permission != original_permission
            or ticket.current is not original_current
            or self._list_context_values(ticket.current) != original_values
            or ticket.managed is not original_managed
            or ticket.native_identity is not original_native
            or ticket.cookie_identity is not original_cookie
            or ticket.session is not session
            or ticket.transaction is not self._list_transaction(session)
            or ticket.actor != actor
            or ticket.permission != "accounts.read"
            or ticket.native_identity is not current_auth_snapshot()
            or ticket.cookie_identity is not current_cookie_identity()
        ):
            invalid()
        await ensure_cookie_current(session, actor)
        if (
            ticket.transaction is not self._list_transaction(session)
            or ticket.native_identity is not current_auth_snapshot()
            or ticket.cookie_identity is not current_cookie_identity()
        ):
            invalid()
        return ticket.current

    async def prepare_for_list(self, session, actor, account_ids, ticket):
        if type(ticket) is not _ListAuthorizationTicket:
            invalid()
        return await self._prepare(
            session, actor, account_ids, "accounts.read", _list_authorization=ticket
        )

    async def _prepare(
        self, session, actor, account_ids, permission, extra_release=(), *, _list_authorization=None
    ):
        tx = transaction(session)
        ids = identifiers(account_ids)
        if _list_authorization is not None:
            if permission != "accounts.read" or extra_release:
                invalid()
            current = await self._consume_list_authorization(session, actor, _list_authorization)
        else:
            current = await require_business_access(session, actor, "accounts", permission)
        probes = (
            await rows(
                session,
                "SELECT h.account_id,h.revision,v.evidence_id,p.release_id "
                "FROM orbit_account_identity_head h JOIN orbit_account_identity_history v "
                "ON v.tenant_id=h.tenant_id AND v.account_id=h.account_id "
                "AND v.revision=h.revision "
                "LEFT JOIN orbit_identity_publication_provenance p ON p.tenant_id=v.tenant_id "
                "AND p.evidence_id=v.evidence_id WHERE h.tenant_id=:tenant "
                "AND h.account_id IN :ids",
                {"tenant": current.tenant_id},
                ids=ids,
            )
            if ids
            else []
        )
        # 只有唯一当前READ来源可能有效；至多2条即可判断歧义，不锁全租户发行历史。
        configurations = await rows(
            session,
            "SELECT id,revision,settings_json,secrets_json FROM "
            "orbit_system_configuration FORCE INDEX(PRIMARY) WHERE tenant_id=:tenant "
            "AND section='META_BM' AND enabled=1 AND verification_status='READ_VERIFIED' "
            "ORDER BY id LIMIT 2 FOR SHARE",
            {"tenant": current.tenant_id},
        )
        release_ids = sorted(
            {row["release_id"] for row in probes if row["release_id"]} | set(extra_release)
        )
        if len(release_ids) > 200:
            invalid()
        releases = (
            await rows(
                session,
                "SELECT * FROM orbit_identity_capability_release FORCE INDEX(PRIMARY) "
                "WHERE tenant_id=:tenant AND id IN :ids ORDER BY id FOR SHARE",
                {"tenant": current.tenant_id},
                ids=release_ids,
            )
            if release_ids
            else []
        )
        configs = tuple(
            MappingProxyType(
                {
                    k: canonical(v) if k.endswith("_json") and isinstance(v, dict) else v
                    for k, v in row.items()
                }
            )
            for row in configurations
        )
        return SummaryTicket(
            session,
            tx,
            current,
            permission,
            ids,
            MappingProxyType(
                {
                    row["account_id"]: tuple(
                        row[k] for k in ("revision", "evidence_id", "release_id")
                    )
                    for row in probes
                }
            ),
            configs,
            MappingProxyType({row["id"]: MappingProxyType(dict(row)) for row in releases}),
            _ISSUER,
        )

    async def prepare(self, session, actor, candidate_ids):
        """仅列表当前auth→probe→来源；调用方必须在任何clock锁前调用。"""
        return await self._prepare(session, actor, candidate_ids, "accounts.read")

    async def prepare_publication(self, session, actor, prepared):
        """未来原事务wrapper：先成功metadata probe，再本方法，后C1 register/seal。

        仅sync动作，不额外借read。来源先锁后直接UPDATE clock，避免成功重放后SHARE升级。
        """
        IdentityPublicationStore.check(prepared)
        ticket = await self._prepare(
            session,
            actor,
            [prepared.qualification.account_id],
            "accounts.sync",
            (prepared.qualification.release_id,),
        )
        await clock(session, ticket.current, write=True)
        return ticket

    def check_ticket(self, session, actor, ticket, permission):
        if (
            not isinstance(ticket, SummaryTicket)
            or ticket._issuer is not _ISSUER
            or (
                ticket.session is not session
                or ticket.transaction is not transaction(session)
                or ticket.current.actor_id != actor
                or ticket.permission != permission
            )
        ):
            invalid()

    async def _metadata(self, session, current, ids):
        p = {"tenant": current.tenant_id}
        heads = await rows(
            session,
            "SELECT h.account_id,h.revision,v.evidence_id,v.capability_version,"
            "v.resource_count,v.observed_at,v.provenance_frozen FROM orbit_account_identity_head h "
            "JOIN orbit_account_identity_history v ON v.tenant_id=h.tenant_id "
            "AND v.account_id=h.account_id "
            "AND v.revision=h.revision WHERE h.tenant_id=:tenant AND h.account_id IN :ids "
            "ORDER BY h.account_id FOR SHARE OF h,v",
            p,
            ids=ids,
        )
        evidence_ids = sorted({row["evidence_id"] for row in heads})
        evidence = (
            await rows(
                session,
                "SELECT * FROM orbit_account_identity_evidence WHERE tenant_id=:tenant "
                "AND id IN :ids ORDER BY id FOR SHARE",
                p,
                ids=evidence_ids,
            )
            if evidence_ids
            else []
        )
        proof = (
            await rows(
                session,
                "SELECT * FROM orbit_identity_publication_provenance WHERE tenant_id=:tenant "
                "AND evidence_id IN :ids ORDER BY evidence_id FOR SHARE",
                p,
                ids=evidence_ids,
            )
            if evidence_ids
            else []
        )
        seals = (
            await rows(
                session,
                "SELECT * FROM orbit_identity_inventory_seal WHERE tenant_id=:tenant "
                "AND evidence_id IN :ids ORDER BY evidence_id FOR SHARE",
                p,
                ids=evidence_ids,
            )
            if evidence_ids
            else []
        )
        raw_ids = sorted({row["registry_id"] for row in proof})
        raw = (
            await rows(
                session,
                "SELECT id,bound_sha256,source_config_id,source_config_revision "
                "FROM orbit_meta_raw_head WHERE tenant_id=:tenant "
                "AND id IN :ids ORDER BY id FOR SHARE",
                p,
                ids=raw_ids,
            )
            if raw_ids
            else []
        )
        return (
            {r["account_id"]: r for r in heads},
            {r["id"]: r for r in evidence},
            {r["evidence_id"]: r for r in proof},
            {r["evidence_id"]: r for r in seals},
            {r["id"]: r for r in raw},
        )

    def _expected(self, current, account, head, evidence, proof, key_id):
        if head["provenance_frozen"] != 1 or evidence["complete"] != 1 or evidence["verified"] != 1:
            invalid()
        if (
            (
                proof["tenant_id"],
                proof["account_id"],
                proof["identity_revision"],
                proof["evidence_id"],
            )
            != (current.tenant_id, account["id"], head["revision"], head["evidence_id"])
            or (
                evidence["account_id"],
                evidence["account_revision"],
                evidence["capability_version"],
            )
            != (account["id"], account["revision"], head["capability_version"])
            or evidence["payload_hash"] != proof["payload_hash"]
            or database_time(evidence["observed_at"]) != database_time(head["observed_at"])
        ):
            invalid()
        value = {key: proof[key] for key in CLAIM_FIELDS if key in proof}
        value.update(
            tenant_id=current.tenant_id,
            account_id=account["id"],
            revision=head["revision"],
            source_config_id=evidence["source_config_id"],
            source_config_revision=evidence["source_config_revision"],
            account_revision=evidence["account_revision"],
            capability_version=head["capability_version"],
            resource_count=head["resource_count"],
            observed_at=evidence["observed_at"],
            key_id=key_id,
        )
        return value

    def _live(self, ticket, account, evidence, proof, raw, now):
        if (
            len(ticket.configurations) != 1
            or raw is None
            or account["unbound_at"] is not None
            or (account["auth_status"], account["account_status"]) != ("AUTHORIZED", "ACTIVE")
            or evidence["revoked_at"] is not None
        ):
            invalid()
        config = ticket.configurations[0]
        settings, secrets = _decode(config["settings_json"]), _decode(config["secrets_json"])
        if (
            not isinstance(settings, dict)
            or not isinstance(secrets, dict)
            or not secrets.get("accessToken")
            or (config["id"], config["revision"], settings.get("systemUserId"))
            != (
                evidence["source_config_id"],
                evidence["source_config_revision"],
                proof["principal_id"],
            )
        ):
            invalid()
        valid_release(
            ticket.releases.get(proof["release_id"]),
            config,
            kind=proof["authority_kind"],
            version=evidence["capability_version"],
            revision=proof["release_revision"],
            source_hash=proof["release_source_hash"],
            business=settings.get("businessId"),
            graph=settings.get("graphVersion"),
        )
        if (raw["bound_sha256"], raw["source_config_id"], raw["source_config_revision"]) != (
            proof["bound_sha256"],
            evidence["source_config_id"],
            evidence["source_config_revision"],
        ) or database_time(proof["raw_observed_at"]) > now:
            invalid()
        expiry = evidence["credential_expires_at"]
        raw_expiry = proof["raw_credential_expires_at"]
        if (
            (database_time(expiry) if expiry is not None else None)
            != (floor_ms(database_time(raw_expiry)) if raw_expiry is not None else None)
            or expiry is not None
            and database_time(expiry) <= now
        ):
            invalid()

    async def resolve(self, session, actor, page, ticket):
        self.check_ticket(session, actor, ticket, "accounts.read")
        ids = identifiers([r["id"] for r in page])
        current = await require_business_access(session, actor, "accounts", "accounts.read")
        if current != ticket.current:
            invalid()
        await clock(session, current)
        accounts = {r["id"]: r for r in await current_accounts(session, current, ids)}
        if not ids:
            return {}
        heads, evidence, proofs, seals, raw = await self._metadata(session, current, ids)
        now = database_time((await session.execute(text("SELECT UTC_TIMESTAMP(6)"))).scalar_one())
        result, allowed_kinds = {}, {}
        for identifier in ids:
            head = heads.get(identifier)
            result[identifier] = unknown("UNSYNCED" if head is None else "UNKNOWN")
            if head is None:
                continue
            try:
                proof, item, seal = (
                    proofs[head["evidence_id"]],
                    evidence[head["evidence_id"]],
                    seals[head["evidence_id"]],
                )
                if ticket.probes.get(identifier) != (
                    head["revision"],
                    head["evidence_id"],
                    proof["release_id"],
                ):
                    continue
                kind = proof["authority_kind"]
                if kind not in allowed_kinds:
                    try:
                        await authority_database(session, kind)
                        allowed_kinds[kind] = True
                    except OrbitError:
                        allowed_kinds[kind] = False
                if not allowed_kinds[kind]:
                    continue
                self._live(
                    ticket, accounts[identifier], item, proof, raw.get(proof["registry_id"]), now
                )
                expected = self._expected(
                    current, accounts[identifier], head, item, proof, seal["key_id"]
                )
                if not matches_current_seal(self.cipher, expected, seal):
                    continue
                result[identifier] = {
                    "identity_status": "SYNCED",
                    "identity_count": expected["resource_count"],
                    "identity_observed_at": iso(database_time(expected["observed_at"])),
                }
            except (OrbitError, KeyError, TypeError, ValueError, UnicodeError):
                # 非完整来源/坏seal仅该行未知；current auth/scope与dueguard错误在循环外传播。
                continue
        return result

    async def seal_published(self, session, actor, prepared, receipt, ticket):
        """待主线接入同事务wrapper；不能独立在持clock后首次拿source锁。

        先store.successful_replay；未命中才prepare_publication→store.register→本方法→外层commit。
        仅后台显式重算完整body；默认无key不生成seal，也不标摘要成功。
        """
        self.check_ticket(session, actor, ticket, "accounts.sync")
        if self.cipher is None or not self.cipher.ready:
            return False
        expected_payload = IdentityPublicationStore.check(prepared)
        current = await require_business_access(session, actor, "accounts", "accounts.sync")
        if current != ticket.current:
            invalid()
        if (
            receipt.get("account_id") != prepared.qualification.account_id
            or receipt.get("revision") != prepared.expected_revision + 1
        ):
            invalid()
        ids = [prepared.qualification.account_id]
        accounts = await current_accounts(session, current, ids, write=True)
        # 当前E→H，避免与E已知撤销的E→H守护形成合法倒序。
        await rows(
            session,
            "SELECT id FROM orbit_account_identity_evidence WHERE tenant_id=:tenant "
            "AND id IN :ids ORDER BY id FOR SHARE",
            {"tenant": current.tenant_id},
            ids=[receipt["evidence_id"]],
        )
        await rows(
            session,
            "SELECT revision FROM orbit_account_identity_history WHERE tenant_id=:tenant "
            "AND account_id IN :ids AND revision=:revision ORDER BY account_id FOR UPDATE",
            {"tenant": current.tenant_id, "revision": receipt["revision"]},
            ids=ids,
        )
        heads, evidence, proofs, seals, raw = await self._metadata(session, current, ids)
        head = heads[ids[0]]
        if (head["evidence_id"], head["revision"]) != (
            receipt["evidence_id"],
            prepared.expected_revision + 1,
        ):
            return False  # 旧成功回执不替另一个当前head签署摘要。
        proof, item = proofs[head["evidence_id"]], evidence[head["evidence_id"]]
        await authority_database(session, proof["authority_kind"])
        if proof["intent_hash"] != prepared.intent_hash or proof["payload_hash"] != fingerprint(
            expected_payload
        ):
            invalid()
        now = database_time((await session.execute(text("SELECT UTC_TIMESTAMP(6)"))).scalar_one())
        self._live(ticket, accounts[0], item, proof, raw.get(proof["registry_id"]), now)
        await verify_history(session, current, proof, canonical(expected_payload))
        if head["evidence_id"] in seals:
            old = seals[head["evidence_id"]]
            expected = self._expected(current, accounts[0], head, item, proof, old["key_id"])
            return matches_current_seal(self.cipher, expected, old)
        values = self._expected(current, accounts[0], head, item, proof, self.cipher.active_key_id)
        values["mac"] = self.cipher.application_mac(
            PURPOSE, canonical(seal_claims(values)).encode("utf-8"), values["key_id"]
        )
        await session.execute(
            text(
                "INSERT INTO orbit_identity_inventory_seal("
                + ",".join(CLAIM_FIELDS)
                + ",mac) VALUES("
                + ",".join(":" + k for k in CLAIM_FIELDS)
                + ",:mac)"
            ),
            values,
        )
        return True
