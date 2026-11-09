"""原AccountIdentities当前读取：有完整053旁证才返回，不继承手工verified布尔。"""

from sqlalchemy import text

from orbit_api.account_access import clock
from orbit_api.account_identities_store import identifier, validate_evidence
from orbit_api.authorization import require_business_access
from orbit_api.configuration_store import _decode
from orbit_api.identity_publication_store import (
    PROJECTION,
    authority_database,
    current_accounts,
    floor_ms,
    lock_sources,
    unavailable,
    valid_release,
    verify_history,
)
from orbit_api.meta_observation_registry import database_time, one


class IdentityPublicationReadmodel:
    async def get(self, session, actor, account_id, *, prepared_sources=None):
        account_id = identifier(account_id, "/id")
        current = await require_business_access(session, actor, "accounts", "accounts.read")
        p = {"tenant": current.tenant_id, "account": account_id}
        # 仅发现需要锁的来源ID，不对客户端返回；真实授权/版本均后续当前锁读。
        if prepared_sources is None:
            probe = await one(
                session,
                "SELECT p.evidence_id,p.release_id FROM orbit_account_identity_head h "
                "JOIN orbit_account_identity_history v ON v.tenant_id=h.tenant_id "
                "AND v.account_id=h.account_id AND v.revision=h.revision "
                "JOIN orbit_identity_publication_provenance p ON p.tenant_id=v.tenant_id "
                "AND p.evidence_id=v.evidence_id WHERE h.tenant_id=:tenant "
                "AND h.account_id=:account",
                p,
            )
            # 无可信来源只核对象可见性，不以空releaseID先查来源，也不在clock之后补来源锁。
            configurations, release = ([], None)
            if probe is not None:
                configurations, release = await lock_sources(session, current, probe["release_id"])
        else:
            # 仅内部草稿引用调用；来源已在任何业务clock之前加锁。
            # 后续当前head与probe不一致仍失败，不为新来源补锁。
            probe = prepared_sources["probe"]
            configurations = prepared_sources["configurations"]
            release = prepared_sources["release"]
        await clock(session, current)
        account = (await current_accounts(session, current, [account_id]))[0]
        if (
            account["auth_status"] != "AUTHORIZED"
            or account["account_status"] != "ACTIVE"
            or account["unbound_at"] is not None
        ):
            unavailable("ACCOUNT_IDENTITY_ACCOUNT_UNAVAILABLE")
        head = await one(
            session,
            "SELECT h.revision,v.evidence_id FROM orbit_account_identity_head h "
            "JOIN orbit_account_identity_history v ON v.tenant_id=h.tenant_id AND "
            "v.account_id=h.account_id "
            "AND v.revision=h.revision WHERE h.tenant_id=:tenant AND h.account_id=:account "
            "FOR SHARE OF h,v",
            p,
        )
        if head is None:
            unavailable("ACCOUNT_IDENTITIES_UNSYNCED")
        if probe is None or head["evidence_id"] != probe["evidence_id"]:
            # 已有不同新来源不能在拿clock后首次补来源锁；新短事务重试。
            unavailable("IDENTITY_PUBLICATION_SOURCE_RETRY")
        proof = await one(
            session,
            "SELECT * FROM orbit_identity_publication_provenance "
            "WHERE tenant_id=:tenant AND evidence_id=:evidence FOR SHARE",
            p | {"evidence": head["evidence_id"]},
        )
        evidence = await one(
            session,
            "SELECT * FROM orbit_account_identity_evidence "
            "WHERE tenant_id=:tenant AND id=:evidence FOR SHARE",
            p | {"evidence": head["evidence_id"]},
        )
        if (
            proof is None
            or evidence is None
            or proof["identity_revision"] != head["revision"]
            or proof["account_id"] != account_id
        ):
            unavailable("IDENTITY_PUBLICATION_HISTORY_INVALID")
        await authority_database(session, proof["authority_kind"])
        if len(configurations) != 1:
            unavailable("ACCOUNT_IDENTITY_SOURCE_UNAVAILABLE")
        config = configurations[0]
        if config["id"] != evidence["source_config_id"]:
            unavailable("ACCOUNT_IDENTITY_SOURCE_UNAVAILABLE")
        settings = _decode(config["settings_json"])
        if not isinstance(settings, dict) or settings.get("systemUserId") != proof["principal_id"]:
            unavailable("ACCOUNT_IDENTITY_SOURCE_UNAVAILABLE")
        valid_release(
            release,
            config,
            kind=proof["authority_kind"],
            version=evidence["capability_version"],
            revision=proof["release_revision"],
            source_hash=proof["release_source_hash"],
            business=settings.get("businessId"),
            graph=settings.get("graphVersion"),
        )
        if (
            proof["release_id"] != probe["release_id"]
            or proof["projection_version"] != PROJECTION
            or (
                floor_ms(database_time(proof["raw_observed_at"]))
                != database_time(evidence["observed_at"])
            )
        ):
            unavailable("IDENTITY_PUBLICATION_HISTORY_INVALID")
        raw_expiry = proof["raw_credential_expires_at"]
        if (floor_ms(database_time(raw_expiry)) if raw_expiry is not None else None) != (
            database_time(evidence["credential_expires_at"])
            if evidence["credential_expires_at"] is not None
            else None
        ):
            unavailable("IDENTITY_PUBLICATION_HISTORY_INVALID")
        raw = await one(
            session,
            "SELECT bound_sha256,source_config_id,source_config_revision FROM orbit_meta_raw_head "
            "WHERE tenant_id=:tenant AND id=:registry FOR SHARE",
            p | {"registry": proof["registry_id"]},
        )
        if raw is None or (
            raw["bound_sha256"],
            raw["source_config_id"],
            raw["source_config_revision"],
        ) != (
            proof["bound_sha256"],
            evidence["source_config_id"],
            evidence["source_config_revision"],
        ):
            unavailable("IDENTITY_PUBLICATION_RAW_UNAVAILABLE")
        value = await verify_history(session, current, proof)
        now = database_time((await session.execute(text("SELECT UTC_TIMESTAMP(6)"))).scalar_one())
        if database_time(proof["raw_observed_at"]) > now:
            unavailable("IDENTITY_PUBLICATION_HISTORY_INVALID")
        validate_evidence(
            evidence,
            account,
            dict(config)
            | {"section": "META_BM", "enabled": 1, "verification_status": "READ_VERIFIED"},
            value,
            now,
        )
        return value
