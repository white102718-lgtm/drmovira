"""账户导入只读Worker：短认领、冻结唯一BM来源、真实读取后原子绑定与历史归属。"""

import json
import secrets
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import text

from orbit_api.account_access import event, visible_clause
from orbit_api.account_alias_snapshots import append_account_alias_snapshot
from orbit_api.account_contract import batch_summary
from orbit_api.account_metadata import metadata, timezone_payload, unknown_observation
from orbit_api.account_platform import (
    AccountReadFailure,
    MetaAccountPlatform,
    MetaReadConfiguration,
)
from orbit_api.authorization import require_business_access
from orbit_api.configuration_store import MAX_REVISION, _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.identity_contract import _uuid
from orbit_api.meta_account_sources import (
    MetaAccountSource,
    MetaAccountSourceReader,
    attach_import_source,
    import_source,
    invalidate_meta_read_source,
    load_connection,
    validate_import_channel,
)
from orbit_api.reference_access import managed_teams, readable, validate_ownership
from orbit_api.reference_store import records


@dataclass(frozen=True, repr=False)
class AccountClaim:
    tenant: str
    batch_id: str
    row_id: str
    revision: int
    request_id: str
    external_id: str
    source_id: str
    source_revision: int
    configuration: MetaReadConfiguration | MetaAccountSource
    identifiers: tuple[str, ...]


def retry_delay(attempt):
    if type(attempt) is not int or not 1 <= attempt <= 3:
        raise ValueError("只读重试次数必须1至3")
    return (30, 60, 120)[attempt - 1] + secrets.randbelow(11)


class AccountImportWorker:
    """不会自动启动或调用平台写方法；平台读取替换必须显式注入，仅用于隔离协议验收。"""

    def __init__(
        self,
        sessions,
        cipher,
        currencies,
        *,
        platform_factory=MetaAccountPlatform,
        target=None,
        meta_graph_version=None,
        meta_adapter_factory=None,
    ):
        self.sessions, self.cipher = sessions, cipher
        self.currencies, self.platform_factory = frozenset(currencies), platform_factory
        self.meta_graph_version, self.meta_adapter_factory = (
            meta_graph_version,
            meta_adapter_factory,
        )
        if target is not None and (not isinstance(target, tuple) or len(target) != 2):
            raise ValueError("受控批次目标必须为租户与批次两个UUID")
        self.target = (
            (_uuid(target[0], "/tenant_id"), _uuid(target[1], "/batch_id"))
            if target is not None
            else None
        )

    def target_filter(self):
        if self.target is None:
            return "", {}
        return " AND tenant_id=:target_tenant AND batch_id=:target_batch", {
            "target_tenant": self.target[0],
            "target_batch": self.target[1],
        }

    @staticmethod
    def audit_context(batch):
        # 只给事件写入使用的冻结发起人，不把Worker当作具备SUPER_ADMIN的请求会话。
        return SimpleNamespace(
            tenant_id=batch["tenant_id"],
            actor_id=batch["actor_id"],
            subject_id=batch["actor_subject_id"],
        )

    async def lock_batch(self, session, tenant, identifier):
        # 顺序固定为租户账户时钟→批次→行，避免与HTTP受理/幂等重放形成相反锁序。
        version = (
            await session.execute(
                text(
                    "SELECT revision FROM orbit_account_clock "
                    "WHERE tenant_id=:tenant FOR UPDATE SKIP LOCKED"
                ),
                {"tenant": tenant},
            )
        ).scalar_one_or_none()
        if version is None:
            return None
        if version >= MAX_REVISION - 2:
            raise OrbitError(409, "REVISION_EXHAUSTED", "账户目录版本已达任务上限")
        # 与公共读取同一失败关闭口径；当前投影未追平时不能沿旧owner绑定或返回资料。
        # 分配恢复器使用独立锁链，不经这里，因此不会被自己的待办阻断。
        from orbit_api.account_actions_store import require_tenant_projections_current

        await require_tenant_projections_current(session, tenant, datetime.now(UTC))
        return (
            (
                await session.execute(
                    text(
                        "SELECT * FROM orbit_account_import "
                        "WHERE tenant_id=:tenant AND id=:id FOR UPDATE"
                    ),
                    {"tenant": tenant, "id": identifier},
                )
            )
            .mappings()
            .first()
        )

    async def verify(self, session, batch, *, freeze=False, require_source=True):
        try:
            current = await require_business_access(
                session, batch["actor_id"], "accounts", "accounts.import", acting_subject=False
            )
            if (
                current.tenant_id != batch["tenant_id"]
                or current.subject_id != batch["actor_subject_id"]
            ):
                raise AccountReadFailure("ACCOUNT_IMPORT_AUTHORIZATION_CHANGED")
            directory = (
                await session.execute(
                    text(
                        "SELECT revision FROM orbit_directory_clock "
                        "WHERE tenant_id=:tenant FOR SHARE"
                    ),
                    {"tenant": batch["tenant_id"]},
                )
            ).scalar_one()
            if directory != batch["scope_version"]:
                raise AccountReadFailure("ACCOUNT_IMPORT_AUTHORIZATION_CHANGED")
            version = (
                await session.execute(
                    text(
                        "SELECT auth_version FROM sys_identity_subject "
                        "WHERE user_id=:actor FOR SHARE"
                    ),
                    {"actor": batch["actor_id"]},
                )
            ).scalar_one()
            if batch["actor_auth_version"] is not None and batch["actor_auth_version"] != version:
                raise AccountReadFailure("ACCOUNT_IMPORT_AUTHORIZATION_CHANGED")
            await validate_ownership(
                session,
                current,
                {
                    "owner_team_id": batch["owner_team_id"],
                    "data_owner_user_ids": [batch["owner_user_id"]],
                },
            )
            vendor = (await records(session, current.tenant_id, [batch["vendor_id"]])).get(
                batch["vendor_id"]
            )
            if vendor is None or vendor["kind"] != "VENDOR":
                raise AccountReadFailure("ACCOUNT_IMPORT_REFERENCE_CHANGED")
            value = _decode(vendor["value_json"])
            if value["availability"] != "AVAILABLE":
                raise AccountReadFailure("VENDOR_DISABLED")
            if (
                vendor["revision"] != batch["vendor_revision"]
                or value["owner_team_id"] != batch["owner_team_id"]
                or batch["owner_user_id"] not in value["data_owner_user_ids"]
                or not readable(current, await managed_teams(session, current), value)
            ):
                raise AccountReadFailure("ACCOUNT_IMPORT_REFERENCE_CHANGED")
            selected = await import_source(session, current.tenant_id, batch["id"])
            if selected is not None:
                configuration = await load_connection(
                    session,
                    self.cipher,
                    current.tenant_id,
                    selected["connection_id"],
                    selected["connection_revision"],
                    self.meta_graph_version,
                )
                await validate_import_channel(session, current, selected["channel_id"])
                configuration = replace(
                    configuration, import_selection=(selected["revision"], selected["channel_id"])
                )
                if batch["source_config_id"] is not None and (
                    batch["source_config_id"] != selected["connection_id"]
                    or batch["source_config_revision"] != selected["connection_revision"]
                ):
                    raise AccountReadFailure("ACCOUNT_IMPORT_SOURCE_CHANGED")
                if batch["source_config_id"] is None and require_source:
                    if not freeze:
                        raise AccountReadFailure("ACCOUNT_IMPORT_SOURCE_UNFROZEN")
                    request_id = str(uuid4())
                    await session.execute(
                        text(
                            "UPDATE orbit_account_import SET source_config_id=:source,"
                            "source_config_revision=:revision,actor_auth_version=:auth,"
                            "request_id=:request "
                            "WHERE tenant_id=:tenant AND id=:id AND source_config_id IS NULL"
                        ),
                        {
                            "tenant": current.tenant_id,
                            "id": batch["id"],
                            "source": selected["connection_id"],
                            "revision": selected["connection_revision"],
                            "auth": version,
                            "request": request_id,
                        },
                    )
                    batch = dict(batch) | {
                        "source_config_id": selected["connection_id"],
                        "source_config_revision": selected["connection_revision"],
                        "actor_auth_version": version,
                        "request_id": request_id,
                    }
                return current, batch, configuration if require_source else None
            if not require_source:
                # 已有账户可免平台读取，但不能绕过已停用户商/变化归属的实时复核。
                return current, batch, None
            if batch["source_config_id"] is None:
                if not freeze:
                    raise AccountReadFailure("ACCOUNT_IMPORT_SOURCE_UNFROZEN")
                sources = list(
                    (
                        await session.execute(
                            text("""SELECT id,revision,settings_json,secrets_json
                    FROM orbit_system_configuration WHERE tenant_id=:tenant AND section='META_BM'
                    AND enabled=1 AND verification_status='READ_VERIFIED'
                    ORDER BY id LIMIT 2 FOR SHARE"""),
                            {"tenant": current.tenant_id},
                        )
                    ).mappings()
                )
                if len(sources) != 1:
                    raise AccountReadFailure(
                        "ACCOUNT_IMPORT_SOURCE_REQUIRED"
                        if not sources
                        else "ACCOUNT_IMPORT_SOURCE_AMBIGUOUS"
                    )
                source = sources[0]
                request_id = str(uuid4())
                await session.execute(
                    text("""UPDATE orbit_account_import SET source_config_id=:source,
                    source_config_revision=:revision,actor_auth_version=:auth,request_id=:request
                    WHERE tenant_id=:tenant AND id=:id AND source_config_id IS NULL"""),
                    {
                        "tenant": current.tenant_id,
                        "id": batch["id"],
                        "source": source["id"],
                        "revision": source["revision"],
                        "auth": version,
                        "request": request_id,
                    },
                )
                batch = dict(batch) | {
                    "source_config_id": source["id"],
                    "source_config_revision": source["revision"],
                    "actor_auth_version": version,
                    "request_id": request_id,
                }
            else:
                source = (
                    (
                        await session.execute(
                            text("""SELECT id,revision,settings_json,secrets_json
                    FROM orbit_system_configuration WHERE tenant_id=:tenant AND id=:id
                    AND section='META_BM' AND enabled=1 AND verification_status='READ_VERIFIED'
                    AND revision=:revision FOR SHARE"""),
                            {
                                "tenant": current.tenant_id,
                                "id": batch["source_config_id"],
                                "revision": batch["source_config_revision"],
                            },
                        )
                    )
                    .mappings()
                    .first()
                )
                if source is None:
                    raise AccountReadFailure("ACCOUNT_IMPORT_SOURCE_CHANGED")
            settings, encrypted = _decode(source["settings_json"]), _decode(source["secrets_json"])
            if not encrypted.get("accessToken") or not self.cipher.ready:
                raise AccountReadFailure("ACCOUNT_IMPORT_SOURCE_UNAVAILABLE")
            token = self.cipher.decrypt_internal(
                encrypted["accessToken"], current.tenant_id, source["id"], "accessToken"
            )
            configuration = MetaReadConfiguration(
                settings.get("businessId"), settings.get("graphVersion"), token
            )
            configuration.validate()
            return current, batch, configuration
        except OrbitError as error:
            code = (
                "ACCOUNT_IMPORT_SOURCE_UNAVAILABLE"
                if error.status == 503
                else "ACCOUNT_IMPORT_AUTHORIZATION_CHANGED"
            )
            raise AccountReadFailure(code) from None

    async def record(
        self,
        session,
        batch,
        row,
        state,
        *,
        code=None,
        retryable=False,
        account=None,
        name=None,
        currency="XXX",
        delay=None,
        observed_at=None,
    ):
        if row["revision"] >= MAX_REVISION or batch["revision"] >= MAX_REVISION:
            raise OrbitError(409, "REVISION_EXHAUSTED", "导入版本已达上限")
        value = dict(_decode(row["value_json"]))
        value.update(
            {
                "state": state,
                "account_id": account,
                # ImportRow展示名合同最多255字；账户原始名称另行完整保存。
                "name": name[:255] if name is not None else None,
                "error_code": code,
                "retryable": retryable,
                "spend": unknown_observation(currency, kind="SPEND"),
                "observed_at": observed_at,
            }
        )
        await session.execute(
            text("""UPDATE orbit_account_import_row SET state=:state,revision=revision+1,
            value_json=:value,next_attempt_at=IF(:delay IS NULL,NULL,
                TIMESTAMPADD(SECOND,:delay,UTC_TIMESTAMP(3)))
            WHERE tenant_id=:tenant AND id=:id AND revision=:revision"""),
            {
                "tenant": row["tenant_id"],
                "id": row["id"],
                "revision": row["revision"],
                "state": state,
                "value": canonical(value),
                "delay": delay,
            },
        )
        actor = self.audit_context(batch)
        request_id = row["claim_request_id"] or batch["request_id"] or str(uuid4())
        await event(
            session,
            actor,
            "IMPORT_ROW",
            row["id"],
            row["revision"] + 1,
            "IMPORT_ROW_" + state,
            request_id,
            {"state": state, "code": code},
        )
        states = list(
            (
                await session.execute(
                    text(
                        "SELECT state FROM orbit_account_import_row "
                        "WHERE tenant_id=:tenant AND batch_id=:batch ORDER BY token_index"
                    ),
                    {"tenant": row["tenant_id"], "batch": batch["id"]},
                )
            ).scalars()
        )
        summary = batch_summary(states)
        await session.execute(
            text("""UPDATE orbit_account_import SET revision=revision+1,state=:state,
            success_count=:success_count,failed_count=:failed_count,duplicate_count=:duplicate_count,
            updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=:tenant AND id=:id"""),
            {"tenant": row["tenant_id"], "id": batch["id"]} | summary,
        )
        await event(
            session,
            actor,
            "IMPORT",
            batch["id"],
            batch["revision"] + 1,
            "IMPORT_PROGRESS",
            request_id,
            summary,
        )

    async def claim_one(self):
        async with self.sessions() as session, session.begin():
            target_sql, target_parameters = self.target_filter()
            candidate = (
                (
                    await session.execute(
                        text(
                            """SELECT tenant_id,batch_id FROM orbit_account_import_row
                WHERE state='WAITING' AND next_attempt_at<=UTC_TIMESTAMP(3)
                """
                            + target_sql
                            + " ORDER BY next_attempt_at,tenant_id,id LIMIT 1"
                        ),
                        target_parameters,
                    )
                )
                .mappings()
                .first()
            )
            if candidate is None:
                return None, False
            batch = await self.lock_batch(session, candidate["tenant_id"], candidate["batch_id"])
            if batch is None:
                return None, False
            row = (
                (
                    await session.execute(
                        text("""SELECT * FROM orbit_account_import_row
                WHERE tenant_id=:tenant AND batch_id=:batch AND state='WAITING'
                AND next_attempt_at<=UTC_TIMESTAMP(3) ORDER BY token_index
                LIMIT 1 FOR UPDATE SKIP LOCKED"""),
                        {"tenant": candidate["tenant_id"], "batch": candidate["batch_id"]},
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                return None, False
            try:
                current, batch, _ = await self.verify(session, batch, require_source=False)
                old = (
                    (
                        await session.execute(
                            text(
                                "SELECT a.* FROM orbit_ad_account a "
                                "WHERE tenant_id=:tenant AND external_id=:external FOR UPDATE"
                            ),
                            {"tenant": row["tenant_id"], "external": row["normalized_id"]},
                        )
                    )
                    .mappings()
                    .first()
                )
                if old is not None:
                    readable_id = (
                        await session.execute(
                            text(
                                "SELECT a.id FROM orbit_ad_account a "
                                "WHERE a.tenant_id=:tenant AND a.id=:id AND ("
                                + visible_clause(current, "a")
                                + ")"
                            ),
                            {
                                "tenant": row["tenant_id"],
                                "id": old["id"],
                                "subject": current.subject_id,
                                "actor": current.actor_id,
                            },
                        )
                    ).scalar_one_or_none()
                    if readable_id is None:
                        await self.record(
                            session, batch, row, "FORBIDDEN", code="ACCOUNT_NOT_READABLE"
                        )
                        return None, True
                    if old["vendor_id"] == batch["vendor_id"]:
                        await self.record(
                            session,
                            batch,
                            row,
                            "ALREADY_EXISTS",
                            account=old["id"],
                            name=old["name"],
                            currency=old["currency"],
                        )
                        return None, True
                    if (
                        old["vendor_id"] is not None
                        or old["owner_user_id"] != batch["owner_user_id"]
                        or old["owner_team_id"] != batch["owner_team_id"]
                    ):
                        await self.record(
                            session,
                            batch,
                            row,
                            "OWNERSHIP_CONFLICT",
                            code="ACCOUNT_OWNERSHIP_CONFLICT",
                        )
                        return None, True
                current, batch, configuration = await self.verify(session, batch, freeze=True)
                if not self.currencies:
                    raise AccountReadFailure("ACCOUNT_CURRENCY_POLICY_REQUIRED")
            except AccountReadFailure as error:
                await self.record(session, batch, row, "FAILED", code=error.code)
                return None, True
            if row["attempts"] >= 4:
                await self.record(
                    session, batch, row, "FAILED", code="ACCOUNT_READ_ATTEMPTS_EXHAUSTED"
                )
                return None, True
            if row["revision"] >= MAX_REVISION - 2:
                raise OrbitError(409, "REVISION_EXHAUSTED", "导入行版本已达任务上限")
            claim_request = str(uuid4())
            await session.execute(
                text("""UPDATE orbit_account_import_row SET attempts=attempts+1,
                claim_request_id=:request,claimed_at=UTC_TIMESTAMP(3)
                WHERE tenant_id=:tenant AND id=:id"""),
                {"tenant": row["tenant_id"], "id": row["id"], "request": claim_request},
            )
            await self.record(
                session, batch, dict(row) | {"claim_request_id": claim_request}, "FETCHING"
            )
            identifiers = tuple(
                (
                    await session.execute(
                        text("""SELECT DISTINCT normalized_id
                FROM orbit_account_import_row WHERE tenant_id=:tenant AND batch_id=:batch
                AND normalized_id IS NOT NULL AND state IN ('WAITING','FETCHING')
                ORDER BY normalized_id"""),
                        {"tenant": row["tenant_id"], "batch": batch["id"]},
                    )
                ).scalars()
            )
            return AccountClaim(
                row["tenant_id"],
                batch["id"],
                row["id"],
                row["revision"] + 1,
                claim_request,
                row["normalized_id"],
                batch["source_config_id"],
                batch["source_config_revision"],
                configuration,
                identifiers,
            ), True

    async def complete(self, claim, result=None, failure=None):
        async with self.sessions() as session, session.begin():
            batch = await self.lock_batch(session, claim.tenant, claim.batch_id)
            if batch is None:
                return False
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM orbit_account_import_row "
                            "WHERE tenant_id=:tenant AND id=:id FOR UPDATE"
                        ),
                        {"tenant": claim.tenant, "id": claim.row_id},
                    )
                )
                .mappings()
                .first()
            )
            if (
                row is None
                or row["state"] != "FETCHING"
                or row["revision"] != claim.revision
                or row["claim_request_id"] != claim.request_id
            ):
                return False
            if (
                batch["source_config_id"] != claim.source_id
                or batch["source_config_revision"] != claim.source_revision
            ):
                await self.record(
                    session, batch, row, "FAILED", code="ACCOUNT_IMPORT_SOURCE_CHANGED"
                )
                return True
            try:
                current, batch, checked = await self.verify(session, batch)
                if (
                    isinstance(claim.configuration, MetaAccountSource)
                    and checked != claim.configuration
                ):
                    raise AccountReadFailure("ACCOUNT_IMPORT_SOURCE_CHANGED")
            except AccountReadFailure as error:
                await self.record(session, batch, row, "FAILED", code=error.code)
                return True
            if failure is not None:
                await invalidate_meta_read_source(
                    session, current, claim.configuration, failure.code, claim.request_id
                )
                retry = failure.retryable and row["attempts"] <= 3
                await self.record(
                    session,
                    batch,
                    row,
                    "WAITING" if retry else "FAILED",
                    code=failure.code,
                    retryable=retry,
                    delay=retry_delay(row["attempts"]) if retry else None,
                )
                return True
            try:
                value = metadata(result, claim.external_id, self.currencies)
            except OrbitError:
                await self.record(session, batch, row, "FAILED", code="ACCOUNT_METADATA_INVALID")
                return True
            old = (
                (
                    await session.execute(
                        text(
                            "SELECT a.* FROM orbit_ad_account a "
                            "WHERE tenant_id=:tenant AND external_id=:external FOR UPDATE"
                        ),
                        {"tenant": claim.tenant, "external": claim.external_id},
                    )
                )
                .mappings()
                .first()
            )
            if old is not None:
                visible = (
                    await session.execute(
                        text(
                            "SELECT a.id FROM orbit_ad_account a "
                            "WHERE a.tenant_id=:tenant AND a.id=:id AND ("
                            + visible_clause(current, "a")
                            + ")"
                        ),
                        {
                            "tenant": claim.tenant,
                            "id": old["id"],
                            "subject": current.subject_id,
                            "actor": current.actor_id,
                        },
                    )
                ).scalar_one_or_none()
                if visible is None:
                    await self.record(session, batch, row, "FORBIDDEN", code="ACCOUNT_NOT_READABLE")
                elif old["vendor_id"] == batch["vendor_id"]:
                    await self.record(
                        session,
                        batch,
                        row,
                        "ALREADY_EXISTS",
                        account=old["id"],
                        name=old["name"],
                        currency=old["currency"],
                    )
                elif (
                    old["vendor_id"] is not None
                    or old["owner_user_id"] != batch["owner_user_id"]
                    or old["owner_team_id"] != batch["owner_team_id"]
                ):
                    await self.record(
                        session, batch, row, "OWNERSHIP_CONFLICT", code="ACCOUNT_OWNERSHIP_CONFLICT"
                    )
                else:
                    # 无户商既有账户只增加允许的户商绑定，不转移任何当前或历史拥有者。
                    if old["revision"] >= MAX_REVISION:
                        raise OrbitError(409, "REVISION_EXHAUSTED", "账户版本已达上限")
                    if old["currency"] != value.currency or old["timezone_id"] != value.timezone_id:
                        await self.record(
                            session, batch, row, "FAILED", code="ACCOUNT_METADATA_CONFLICT"
                        )
                        return True
                    await session.execute(
                        text(
                            "UPDATE orbit_ad_account SET vendor_id=:vendor,revision=revision+1 "
                            "WHERE tenant_id=:tenant AND id=:id"
                        ),
                        {"tenant": claim.tenant, "id": old["id"], "vendor": batch["vendor_id"]},
                    )
                    snapshot_vendor = (await records(session, claim.tenant, [batch["vendor_id"]]))[
                        batch["vendor_id"]
                    ]
                    await append_account_alias_snapshot(
                        session,
                        current,
                        snapshot_vendor,
                        resource_type="ACCOUNT_BINDING",
                        resource_id=old["id"],
                        resource_revision=old["revision"] + 1,
                        request_id=claim.request_id,
                        permission="accounts.import",
                        acting_subject=False,
                    )
                    await event(
                        session,
                        self.audit_context(batch),
                        "ACCOUNT",
                        old["id"],
                        old["revision"] + 1,
                        "ACCOUNT_VENDOR_BOUND",
                        claim.request_id,
                        {"vendor_id": batch["vendor_id"]},
                    )
                    await self.record(
                        session,
                        batch,
                        row,
                        "SUCCEEDED",
                        account=old["id"],
                        name=old["name"],
                        currency=old["currency"],
                    )
                return True
            now = (
                (await session.execute(text("SELECT UTC_TIMESTAMP(3)")))
                .scalar_one()
                .replace(tzinfo=UTC)
            )
            identifier = str(uuid4())
            account = {
                "id": identifier,
                "external_id": value.external_id,
                "name": value.name,
                "ownership": {
                    "owner_user_id": batch["owner_user_id"],
                    "owner_team_id": batch["owner_team_id"],
                },
                "vendor_id": batch["vendor_id"],
                "vendor_alias": None,
                "currency": value.currency,
                "timezone": timezone_payload(value.timezone_id, now),
                "auth_status": value.auth_status,
                "account_status": value.account_status,
                "spend": unknown_observation(value.currency, kind="SPEND"),
                "balance": unknown_observation(value.currency),
                "revision": 1,
                "synced_at": now.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            }
            await session.execute(
                text("""INSERT INTO orbit_ad_account
                (tenant_id,id,external_id,name,name_prefix,owner_user_id,owner_team_id,vendor_id,currency,
                 timezone_id,auth_status,account_status,value_json,details_json,synced_at,bound_at,created_at)
                VALUES(:tenant,:id,:external,:name,:prefix,:owner,:team,:vendor,:currency,:timezone,
                 :auth,:status,:value,:details,:now,:now,:now)"""),
                {
                    "tenant": claim.tenant,
                    "id": identifier,
                    "external": value.external_id,
                    "name": value.name,
                    "prefix": value.name[:191],
                    "owner": batch["owner_user_id"],
                    "team": batch["owner_team_id"],
                    "vendor": batch["vendor_id"],
                    "currency": value.currency,
                    "timezone": value.timezone_id,
                    "auth": value.auth_status,
                    "status": value.account_status,
                    "value": canonical(account),
                    "details": json.dumps(
                        {
                            "source_config_id": claim.source_id,
                            "source_config_revision": claim.source_revision,
                        }
                    ),
                    "now": now.replace(tzinfo=None),
                },
            )
            await attach_import_source(session, current, batch["id"], identifier, claim.request_id)
            local_start = (
                now.astimezone(ZoneInfo(value.timezone_id))
                .replace(hour=0, minute=0, second=0, microsecond=0)
                .astimezone(UTC)
                .replace(tzinfo=None)
            )
            assignment_id = str(uuid4())
            await session.execute(
                text("""INSERT INTO orbit_account_assignment
                (tenant_id,id,account_id,owner_user_id,owner_team_id,vendor_id,starts_at,reason)
                VALUES(:tenant,:id,:account,:owner,:team,:vendor,:starts,'IMPORT_BINDING')"""),
                {
                    "tenant": claim.tenant,
                    "id": assignment_id,
                    "account": identifier,
                    "owner": batch["owner_user_id"],
                    "team": batch["owner_team_id"],
                    "vendor": batch["vendor_id"],
                    "starts": local_start,
                },
            )
            snapshot_vendor = (await records(session, claim.tenant, [batch["vendor_id"]]))[
                batch["vendor_id"]
            ]
            await append_account_alias_snapshot(
                session,
                current,
                snapshot_vendor,
                resource_type="ACCOUNT_BINDING",
                resource_id=identifier,
                resource_revision=1,
                request_id=claim.request_id,
                permission="accounts.import",
                acting_subject=False,
            )
            await append_account_alias_snapshot(
                session,
                current,
                snapshot_vendor,
                resource_type="IMPORT_ASSIGNMENT",
                resource_id=assignment_id,
                resource_revision=1,
                request_id=claim.request_id,
                permission="accounts.import",
                acting_subject=False,
            )
            await event(
                session,
                self.audit_context(batch),
                "ACCOUNT",
                identifier,
                1,
                "ACCOUNT_BOUND",
                claim.request_id,
                {
                    "external_id": value.external_id,
                    "source_id": claim.source_id,
                    "source_revision": claim.source_revision,
                },
            )
            await self.record(
                session,
                batch,
                row,
                "SUCCEEDED",
                account=identifier,
                name=value.name,
                currency=value.currency,
                observed_at=value.observed_at.isoformat(timespec="milliseconds").replace(
                    "+00:00", "Z"
                ),
            )
            return True

    async def preflight(self, claim):
        """每个外部GET之前再做一次短事务复核；事务结束后才进行网络请求。"""
        async with self.sessions() as session, session.begin():
            # 必须先clock再batch/row；若在verify中补clock，会与complete反转锁序。
            version = (
                await session.execute(
                    text(
                        "SELECT revision FROM orbit_account_clock WHERE tenant_id=:tenant FOR SHARE"
                    ),
                    {"tenant": claim.tenant},
                )
            ).scalar_one_or_none()
            if version is None:
                raise OrbitError(503, "ACCOUNT_INITIALIZATION_REQUIRED", "账户目录尚未初始化")
            from orbit_api.account_actions_store import require_tenant_projections_current

            await require_tenant_projections_current(session, claim.tenant, datetime.now(UTC))
            batch = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM orbit_account_import "
                            "WHERE tenant_id=:tenant AND id=:id FOR SHARE"
                        ),
                        {"tenant": claim.tenant, "id": claim.batch_id},
                    )
                )
                .mappings()
                .one()
            )
            row = (
                (
                    await session.execute(
                        text(
                            "SELECT state,revision,claim_request_id "
                            "FROM orbit_account_import_row "
                            "WHERE tenant_id=:tenant AND id=:id FOR SHARE"
                        ),
                        {"tenant": claim.tenant, "id": claim.row_id},
                    )
                )
                .mappings()
                .first()
            )
            if (
                row is None
                or row["state"] != "FETCHING"
                or row["revision"] != claim.revision
                or row["claim_request_id"] != claim.request_id
            ):
                raise AccountReadFailure("ACCOUNT_IMPORT_CLAIM_EXPIRED")
            if (
                batch["source_config_id"] != claim.source_id
                or batch["source_config_revision"] != claim.source_revision
            ):
                raise AccountReadFailure("ACCOUNT_IMPORT_SOURCE_CHANGED")
            _, _, checked = await self.verify(session, batch)
            if (
                isinstance(claim.configuration, MetaAccountSource)
                and checked != claim.configuration
            ):
                raise AccountReadFailure("ACCOUNT_IMPORT_SOURCE_CHANGED")

    async def recover_interrupted(self, limit=100):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("恢复上限必须为1至100")
        recovered = 0
        target_sql, target_parameters = self.target_filter()
        for _ in range(limit):
            async with self.sessions() as session, session.begin():
                candidate = (
                    (
                        await session.execute(
                            text(
                                """SELECT tenant_id,batch_id FROM orbit_account_import_row
                    WHERE state='FETCHING' AND claimed_at<UTC_TIMESTAMP(3)-INTERVAL 120 SECOND
                    """
                                + target_sql
                                + " ORDER BY claimed_at,tenant_id,id LIMIT 1"
                            ),
                            target_parameters,
                        )
                    )
                    .mappings()
                    .first()
                )
                if candidate is None:
                    break
                batch = await self.lock_batch(
                    session, candidate["tenant_id"], candidate["batch_id"]
                )
                if batch is None:
                    break
                row = (
                    (
                        await session.execute(
                            text("""SELECT * FROM orbit_account_import_row
                    WHERE tenant_id=:tenant AND batch_id=:batch AND state='FETCHING'
                    AND claimed_at<UTC_TIMESTAMP(3)-INTERVAL 120 SECOND
                    ORDER BY claimed_at,id LIMIT 1 FOR UPDATE SKIP LOCKED"""),
                            {"tenant": candidate["tenant_id"], "batch": candidate["batch_id"]},
                        )
                    )
                    .mappings()
                    .first()
                )
                if row is None:
                    break
                retry = 1 <= row["attempts"] <= 3
                await self.record(
                    session,
                    batch,
                    row,
                    "WAITING" if retry else "FAILED",
                    code="ACCOUNT_READ_INTERRUPTED",
                    retryable=retry,
                    delay=retry_delay(row["attempts"]) if retry else None,
                )
                recovered += 1
        return recovered

    async def run_once(self, limit=10):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("单轮账户读取批次仅允许1至100")
        recovered = await self.recover_interrupted(limit)
        processed, readers, source_failures = 0, {}, {}
        for _ in range(limit):
            claim, touched = await self.claim_one()
            if not touched:
                break
            processed += 1
            if claim is None:
                continue
            reader_key = (claim.batch_id, claim.source_id, claim.source_revision)
            source_key = (claim.source_id, claim.source_revision)
            try:
                if source_key in source_failures:
                    raise source_failures[source_key]
                if reader_key not in readers:
                    reader = (
                        MetaAccountSourceReader(
                            claim.configuration, adapter_factory=self.meta_adapter_factory
                        )
                        if isinstance(claim.configuration, MetaAccountSource)
                        else self.platform_factory(claim.configuration)
                    )
                    reader.preflight = lambda captured=claim: self.preflight(captured)
                    try:
                        await reader.prepare(claim.identifiers)
                    except AccountReadFailure as error:
                        if error.retryable:
                            source_failures[source_key] = error
                        raise
                    readers[reader_key] = reader
                readers[reader_key].preflight = lambda captured=claim: self.preflight(captured)
                result = await readers[reader_key].fetch_metadata(claim.external_id)
            except AccountReadFailure as error:
                await self.complete(claim, failure=error)
            else:
                await self.complete(claim, result=result)
        return {"processed": processed, "recovered": recovered}
