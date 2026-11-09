"""原身份资源读取与受信发布；没有可信采集证据时失败关闭，不编造资源。"""

import hashlib
from datetime import UTC, datetime

from sqlalchemy import text

from orbit_api.account_access import clock, context, event, parameters, visible_clause
from orbit_api.account_details_contract import iso
from orbit_api.account_identities_contract import identities
from orbit_api.configuration_store import MAX_REVISION, _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.identity_contract import _uuid


def identifier(value, pointer):
    if not isinstance(value, str):
        raise OrbitError(422, "FIELD_INVALID", "请选择有效的业务UUID", pointer)
    return _uuid(value, pointer)


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def unavailable(code="ACCOUNT_IDENTITIES_UNSYNCED"):
    raise OrbitError(503, code, "账户身份资源尚未同步或原能力观察已失效，请重新只读核验")


def fingerprint(value):
    normalized = value | {
        "resources": sorted(
            value["resources"], key=lambda item: (item["kind"], item["external_id"])
        )
    }
    return hashlib.sha256(canonical(normalized).encode("utf-8")).hexdigest()


def validate_evidence(evidence, account, source, value, now):
    """registry必须由真正采集链登记；调用者任意version字符串无法建立有效证据。"""
    if (
        evidence is None
        or not evidence["verified"]
        or not evidence["complete"]
        or evidence["revoked_at"] is not None
        or not evidence["evidence_ref"]
        or evidence["account_id"] != account["id"]
        or evidence["account_revision"] != account["revision"]
    ):
        unavailable("ACCOUNT_IDENTITY_EVIDENCE_UNVERIFIED")
    if (
        source is None
        or source["section"] != "META_BM"
        or not source["enabled"]
        or source["verification_status"] != "READ_VERIFIED"
        or source["revision"] != evidence["source_config_revision"]
        or not _decode(source["secrets_json"]).get("accessToken")
    ):
        unavailable("ACCOUNT_IDENTITY_SOURCE_UNAVAILABLE")
    expiry = evidence["credential_expires_at"]
    if expiry is not None and utc(expiry) <= now:
        unavailable("ACCOUNT_IDENTITY_CREDENTIAL_EXPIRED")
    if (
        evidence["capability_version"] != value["capability_version"]
        or iso(utc(evidence["observed_at"])) != value["observed_at"]
        or evidence["payload_hash"] != fingerprint(value)
        or utc(evidence["observed_at"]) > now
    ):
        unavailable("ACCOUNT_IDENTITY_EVIDENCE_MISMATCH")


class AccountIdentitiesStore:
    async def account(self, session, actor, account_id, *, write=False):
        account_id = identifier(account_id, "/id")
        current, _managed = await context(
            session, actor, "accounts.sync" if write else "accounts.read"
        )
        await clock(session, current, write=write)
        row = (
            (
                await session.execute(
                    text(
                        "SELECT a.id,a.revision,a.auth_status,a.account_status,a.unbound_at "
                        "FROM orbit_ad_account a WHERE a.tenant_id=:tenant AND a.id=:id AND ("
                        + visible_clause(current, "a")
                        + ") "
                        + ("FOR UPDATE OF a" if write else "FOR SHARE OF a")
                    ),
                    parameters(current) | {"id": account_id},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise OrbitError(404, "NOT_FOUND", "账户不存在或不在当前数据范围")
        if (
            row["auth_status"] != "AUTHORIZED"
            or row["account_status"] != "ACTIVE"
            or row["unbound_at"] is not None
        ):
            unavailable("ACCOUNT_IDENTITY_ACCOUNT_UNAVAILABLE")
        return current, row

    async def evidence(self, session, current, evidence_id):
        evidence = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM orbit_account_identity_evidence "
                        "WHERE tenant_id=:tenant AND id=:id FOR SHARE"
                    ),
                    parameters(current) | {"id": evidence_id},
                )
            )
            .mappings()
            .first()
        )
        source = None
        if evidence is not None:
            source = (
                (
                    await session.execute(
                        text(
                            "SELECT section,enabled,verification_status,revision,secrets_json "
                            "FROM orbit_system_configuration "
                            "WHERE tenant_id=:tenant AND id=:id FOR SHARE"
                        ),
                        parameters(current) | {"id": evidence["source_config_id"]},
                    )
                )
                .mappings()
                .first()
            )
        return evidence, source

    async def get(self, session, actor, account_id):
        current, account = await self.account(session, actor, account_id)
        params = parameters(current) | {"id": account["id"]}
        head = (
            (
                await session.execute(
                    text(
                        "SELECT h.revision,h.evidence_id,h.capability_version,h.observed_at,"
                        "h.resource_count FROM orbit_account_identity_head p "
                        "JOIN orbit_account_identity_history h ON h.tenant_id=p.tenant_id "
                        "AND h.account_id=p.account_id AND h.revision=p.revision "
                        "WHERE p.tenant_id=:tenant AND p.account_id=:id FOR SHARE OF p,h"
                    ),
                    params,
                )
            )
            .mappings()
            .first()
        )
        if head is None:
            unavailable()
        rows = list(
            (
                await session.execute(
                    text(
                        "SELECT external_id,name,kind,usable,reason_code "
                        "FROM orbit_account_identity_resource "
                        "WHERE tenant_id=:tenant AND account_id=:id AND revision=:revision "
                        "ORDER BY kind,external_id LIMIT 5001"
                    ),
                    params | {"revision": head["revision"]},
                )
            ).mappings()
        )
        if len(rows) != head["resource_count"] or len(rows) > 5000:
            unavailable("ACCOUNT_IDENTITY_OBSERVATION_INCOMPLETE")
        value = {
            "account_id": account["id"],
            "resources": [dict(row) | {"usable": bool(row["usable"])} for row in rows],
            "capability_version": head["capability_version"],
            "observed_at": iso(utc(head["observed_at"])),
        }
        evidence, source = await self.evidence(session, current, head["evidence_id"])
        validate_evidence(evidence, account, source, value, datetime.now(UTC))
        try:
            return identities(value, expected_account_id=account["id"])
        except OrbitError:
            unavailable("ACCOUNT_IDENTITY_OBSERVATION_INVALID")

    async def publish(self, session, actor, evidence_id, value, expected_revision, request_id):
        """仅受信内部采集调用；不提供registry写入器，也不提供浏览器写身份HTTP。

        fixture直接插入证据只证明本地协议；生产registry/采集缺失时不能发布usable=true。
        执行广告前仍需即时核验，不能拿此GET观察当写授权。
        """
        if not session.in_transaction():
            raise ValueError("身份发布必须与业务审计使用显式外层事务")
        if type(expected_revision) is not int or not 0 <= expected_revision < MAX_REVISION:
            raise OrbitError(422, "FIELD_INVALID", "身份观察版本无效", "/revision")
        evidence_id = identifier(evidence_id, "/evidence_id")
        request_id = identifier(request_id, "/request_id")
        if not isinstance(value, dict):
            raise OrbitError(422, "FIELD_INVALID", "身份观察正文无效")
        account_id = identifier(value.get("account_id"), "/account_id")
        value = identities(value, expected_account_id=account_id)
        # 集合顺序必须稳定，GET与registry摘要一致；不允许用数组顺序改变能力语义。
        value["resources"].sort(key=lambda item: (item["kind"], item["external_id"]))
        current, account = await self.account(session, actor, account_id, write=True)
        evidence, source = await self.evidence(session, current, evidence_id)
        validate_evidence(evidence, account, source, value, datetime.now(UTC))
        params = parameters(current) | {"id": account_id}
        previous = (
            (
                await session.execute(
                    text(
                        "SELECT h.revision,h.observed_at FROM orbit_account_identity_head p "
                        "JOIN orbit_account_identity_history h ON h.tenant_id=p.tenant_id "
                        "AND h.account_id=p.account_id AND h.revision=p.revision "
                        "WHERE p.tenant_id=:tenant AND p.account_id=:id FOR UPDATE OF p"
                    ),
                    params,
                )
            )
            .mappings()
            .first()
        )
        if (previous["revision"] if previous else 0) != expected_revision:
            raise OrbitError(409, "REVISION_CONFLICT", "身份观察版本已更新")
        if previous and utc(evidence["observed_at"]) <= utc(previous["observed_at"]):
            raise OrbitError(409, "OBSERVATION_STALE", "迟到身份观察不能覆盖当前完整版本")
        revision = expected_revision + 1
        values = params | {
            "revision": revision,
            "evidence": evidence_id,
            "version": value["capability_version"],
            "observed": evidence["observed_at"],
            "count": len(value["resources"]),
            "request": request_id,
        }
        await session.execute(
            text(
                "INSERT INTO orbit_account_identity_history "
                "(tenant_id,account_id,revision,evidence_id,capability_version,observed_at,"
                "resource_count,request_id,created_at) VALUES "
                "(:tenant,:id,:revision,:evidence,:version,:observed,:count,:request,UTC_TIMESTAMP(3))"
            ),
            values,
        )
        if value["resources"]:
            await session.execute(
                text(
                    "INSERT INTO orbit_account_identity_resource "
                    "(tenant_id,account_id,revision,kind,external_id,name,usable,reason_code) "
                    "VALUES(:tenant,:id,:revision,:kind,:external_id,:name,:usable,:reason_code)"
                ),
                [values | item for item in value["resources"]],
            )
        await session.execute(
            text(
                "INSERT INTO orbit_account_identity_head(tenant_id,account_id,revision) "
                "VALUES(:tenant,:id,:revision) ON DUPLICATE KEY UPDATE revision=:revision"
            ),
            values,
        )
        await event(
            session,
            current,
            "IDENTITIES",
            account_id,
            revision,
            "ACCOUNT_IDENTITIES_PUBLISHED",
            request_id,
            {"evidence_id": evidence_id, "resource_count": len(value["resources"])},
        )
        return {"revision": revision}
