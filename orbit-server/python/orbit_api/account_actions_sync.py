"""独立持久只读同步执行器；真实BM范围预检，不写广告，不默认启动调度。

事务仅覆盖认领/实时门禁/回写，HTTP期间不持有数据库锁。生产使用现有官方HTTPS
适配器；注入适配器只用于协议验收，不能据此声称真实Meta已连接。
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import text

from orbit_api.account_access import event, visible_clause
from orbit_api.account_actions_store import ownership, require_projection_current
from orbit_api.account_identities_store import identifier, utc
from orbit_api.account_metadata import metadata
from orbit_api.account_platform import (
    AccountReadFailure,
    MetaAccountPlatform,
    MetaReadConfiguration,
)
from orbit_api.authorization import require_business_access
from orbit_api.configuration_store import MAX_REVISION, _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.meta_account_sources import (
    MetaAccountSource,
    MetaAccountSourceReader,
    invalidate_meta_read_source,
    load_sync_source,
)

LEASE_SECONDS = 120
MAX_ATTEMPTS = 4


def retry_at(attempt, now):
    """首次失败后30/60/120秒；第四次失败终态，绝不虚构同步成功。"""
    if type(attempt) is not int or not 1 <= attempt <= MAX_ATTEMPTS:
        raise ValueError("只读尝试次数必须为1至4")
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("重读调度参考时刻必须带时区")
    return (
        now.astimezone(UTC) + timedelta(seconds=(30, 60, 120)[attempt - 1]) if attempt < 4 else None
    )


@dataclass(frozen=True, repr=False)
class SyncClaim:
    tenant: str
    command: str
    account: str
    claim_id: str
    revision: int
    external_id: str
    configuration: MetaReadConfiguration | MetaAccountSource


def claim_matches(command, claim):
    """旧租约、解绑或已终态均不能被迟到读取复活；不依赖调用者的内存状态。"""
    return bool(
        command
        and command["tenant_id"] == claim.tenant
        and command["account_id"] == claim.account
        and command["state"] == "RUNNING"
        and command["active_kind"] == "SYNC"
        and command["claim_id"] == claim.claim_id
        and command["revision"] == claim.revision
    )


class AccountSyncWorker:
    def __init__(
        self,
        sessions,
        cipher,
        currencies,
        tenant_id,
        *,
        platform_factory=MetaAccountPlatform,
        meta_graph_version=None,
        meta_adapter_factory=None,
    ):
        self.sessions, self.cipher = sessions, cipher
        self.currencies = frozenset(currencies)
        self.tenant = identifier(tenant_id, "/tenant_id")
        self.platform_factory = platform_factory
        self.meta_graph_version, self.meta_adapter_factory = (
            meta_graph_version,
            meta_adapter_factory,
        )

    @staticmethod
    def audit(command):
        return SimpleNamespace(
            tenant_id=command["tenant_id"],
            actor_id=command["actor_id"],
            subject_id=command["actor_subject_id"],
        )

    async def lock(self, session, command_id, account_id, *, write):
        lock = "FOR UPDATE" if write else "FOR SHARE"
        version = (
            await session.execute(
                text("SELECT revision FROM orbit_account_clock WHERE tenant_id=:tenant " + lock),
                {"tenant": self.tenant},
            )
        ).scalar_one_or_none()
        if version is None or version >= MAX_REVISION - 2:
            raise OrbitError(503, "ACCOUNT_SYNC_CLOCK_UNAVAILABLE", "同步账户目录版本不可用")
        params = {"tenant": self.tenant, "account": account_id, "command": command_id}
        account = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM orbit_ad_account WHERE tenant_id=:tenant AND id=:account "
                        + lock
                    ),
                    params,
                )
            )
            .mappings()
            .first()
        )
        command = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM orbit_account_command "
                        "WHERE tenant_id=:tenant AND id=:command " + lock
                    ),
                    params,
                )
            )
            .mappings()
            .first()
        )
        return account, command

    async def verify(self, session, account, command, *, claiming=False):
        """每个真正HTTP前和最终回写重复查当前授权、源、归属及账户CAS。"""
        try:
            current = await require_business_access(
                session, command["actor_id"], "accounts", "accounts.sync", acting_subject=False
            )
            if (
                current.tenant_id != self.tenant
                or current.subject_id != command["actor_subject_id"]
            ):
                raise AccountReadFailure("ACCOUNT_SYNC_AUTHORIZATION_CHANGED")
            auth_version = (
                await session.execute(
                    text(
                        "SELECT auth_version FROM sys_identity_subject "
                        "WHERE user_id=:actor FOR SHARE"
                    ),
                    {"actor": current.actor_id},
                )
            ).scalar_one_or_none()
            if auth_version is None or (
                not claiming and auth_version != command["claimed_auth_version"]
            ):
                raise AccountReadFailure("ACCOUNT_SYNC_AUTHORIZATION_CHANGED")
            if account is None or account["unbound_at"] is not None:
                raise AccountReadFailure("ACCOUNT_LOCALLY_UNBOUND")
            visible = (
                await session.execute(
                    text(
                        "SELECT 1 FROM orbit_ad_account a WHERE a.tenant_id=:tenant AND a.id=:id "
                        "AND (" + visible_clause(current, "a") + ") FOR SHARE OF a"
                    ),
                    {
                        "tenant": self.tenant,
                        "id": account["id"],
                        "actor": current.actor_id,
                        "subject": current.subject_id,
                    },
                )
            ).scalar_one_or_none()
            if visible is None:
                raise AccountReadFailure("ACCOUNT_SYNC_SCOPE_CHANGED")
            await require_projection_current(session, self.tenant, account["id"], datetime.now(UTC))
            if ownership(account) != ownership(_decode(command["source_json"])):
                raise AccountReadFailure("ACCOUNT_SYNC_OWNERSHIP_CHANGED")
            if not claiming and account["revision"] != command["claimed_account_revision"]:
                raise AccountReadFailure("ACCOUNT_SYNC_ACCOUNT_CHANGED")
            if account["revision"] >= MAX_REVISION:
                raise AccountReadFailure("ACCOUNT_SYNC_REVISION_EXHAUSTED")
            configuration = await load_sync_source(
                session, self.cipher, self.tenant, account["id"], command, self.meta_graph_version
            )
            if configuration is not None:
                if not self.currencies:
                    raise AccountReadFailure("ACCOUNT_CURRENCY_POLICY_REQUIRED")
                return current, auth_version, configuration
            source = (
                (
                    await session.execute(
                        text(
                            "SELECT id,revision,settings_json,secrets_json "
                            "FROM orbit_system_configuration "
                            "WHERE tenant_id=:tenant AND id=:id AND revision=:revision "
                            "AND section='META_BM' AND enabled=1 "
                            "AND verification_status='READ_VERIFIED' FOR SHARE"
                        ),
                        {
                            "tenant": self.tenant,
                            "id": command["source_config_id"],
                            "revision": command["source_config_revision"],
                        },
                    )
                )
                .mappings()
                .first()
            )
            if source is None:
                raise AccountReadFailure("ACCOUNT_SYNC_SOURCE_CHANGED")
            settings, encrypted = _decode(source["settings_json"]), _decode(source["secrets_json"])
            if (
                not isinstance(encrypted, dict)
                or not encrypted.get("accessToken")
                or not self.cipher.ready
            ):
                raise AccountReadFailure("ACCOUNT_SYNC_SOURCE_UNAVAILABLE")
            token = self.cipher.decrypt_internal(
                encrypted["accessToken"], self.tenant, source["id"], "accessToken"
            )
            configuration = MetaReadConfiguration(
                settings.get("businessId"), settings.get("graphVersion"), token
            )
            configuration.validate()
            if not self.currencies:
                raise AccountReadFailure("ACCOUNT_CURRENCY_POLICY_REQUIRED")
            return current, auth_version, configuration
        except OrbitError as error:
            code = (
                "ACCOUNT_ASSIGNMENT_PROJECTION_LAG"
                if error.code == "ACCOUNT_ASSIGNMENT_PROJECTION_LAG"
                else "ACCOUNT_SYNC_SOURCE_UNAVAILABLE"
                if error.status == 503
                else "ACCOUNT_SYNC_AUTHORIZATION_CHANGED"
            )
            raise AccountReadFailure(code) from None
        except (AttributeError, TypeError, ValueError):
            raise AccountReadFailure("ACCOUNT_SYNC_SOURCE_UNAVAILABLE") from None

    async def transition(self, session, command, state, *, code=None, next_at=None):
        if command["revision"] >= MAX_REVISION:
            raise OrbitError(409, "REVISION_EXHAUSTED", "同步命令版本已达上限")
        terminal = state in {"FAILED", "SUCCEEDED"}
        await session.execute(
            text(
                "UPDATE orbit_account_command SET state=:state,revision=revision+1,"
                "active_kind=:active,last_error_code=:code,next_attempt_at=:next,claim_id=NULL,"
                "claimed_at=NULL,updated_at=UTC_TIMESTAMP(3),completed_at="
                + ("UTC_TIMESTAMP(3)" if terminal else "NULL")
                + " WHERE tenant_id=:tenant AND id=:id"
            ),
            {
                "tenant": self.tenant,
                "id": command["id"],
                "state": state,
                "active": None if terminal else "SYNC",
                "code": code,
                "next": next_at.replace(tzinfo=None) if next_at else None,
            },
        )
        await event(
            session,
            self.audit(command),
            "COMMAND",
            command["id"],
            command["revision"] + 1,
            "ACCOUNT_SYNC_" + state,
            command["request_id"],
            {"code": code},
        )

    async def claim(self):
        async with self.sessions() as session, session.begin():
            candidate = (
                (
                    await session.execute(
                        text(
                            "SELECT id,account_id FROM orbit_account_command "
                            "WHERE tenant_id=:tenant AND kind='SYNC' AND active_kind='SYNC' "
                            "AND ((state IN ('WAITING_EXECUTOR','WAITING_RETRY') "
                            "AND (next_attempt_at IS NULL OR next_attempt_at<=UTC_TIMESTAMP(3))) "
                            "OR (state='RUNNING' "
                            "AND claimed_at<=UTC_TIMESTAMP(3)-INTERVAL 120 SECOND)) "
                            "ORDER BY created_at,id LIMIT 1"
                        ),
                        {"tenant": self.tenant},
                    )
                )
                .mappings()
                .first()
            )
            if candidate is None:
                return None, False
            account, command = await self.lock(
                session, candidate["id"], candidate["account_id"], write=True
            )
            now = utc((await session.execute(text("SELECT UTC_TIMESTAMP(3)"))).scalar_one())
            if command is None or command["active_kind"] != "SYNC":
                return None, True
            if command["state"] == "RUNNING":
                if utc(command["claimed_at"]) + timedelta(seconds=LEASE_SECONDS) > now:
                    return None, False
                due = retry_at(command["attempt_count"], now)
                await self.transition(
                    session,
                    command,
                    "WAITING_RETRY" if due else "FAILED",
                    code="ACCOUNT_SYNC_READ_LEASE_EXPIRED",
                    next_at=due,
                )
                return None, True
            if command["state"] not in {"WAITING_EXECUTOR", "WAITING_RETRY"} or (
                command["next_attempt_at"] and utc(command["next_attempt_at"]) > now
            ):
                return None, False
            if command["attempt_count"] >= MAX_ATTEMPTS:
                await self.transition(
                    session, command, "FAILED", code="ACCOUNT_READ_ATTEMPTS_EXHAUSTED"
                )
                return None, True
            try:
                current, auth_version, configuration = await self.verify(
                    session, account, command, claiming=True
                )
            except AccountReadFailure as failure:
                await self.transition(session, command, "FAILED", code=failure.code)
                return None, True
            claim_id = str(uuid4())
            if command["revision"] >= MAX_REVISION:
                raise OrbitError(409, "REVISION_EXHAUSTED", "同步命令版本已达上限")
            await session.execute(
                text(
                    "UPDATE orbit_account_command SET state='RUNNING',revision=revision+1,"
                    "attempt_count=attempt_count+1,"
                    "claim_id=:claim,claimed_at=:now,claimed_account_revision=:account_revision,"
                    "claimed_auth_version=:auth,next_attempt_at=NULL,"
                    "last_error_code=NULL,updated_at=:now "
                    "WHERE tenant_id=:tenant AND id=:id"
                ),
                {
                    "tenant": self.tenant,
                    "id": command["id"],
                    "claim": claim_id,
                    "now": now.replace(tzinfo=None),
                    "account_revision": account["revision"],
                    "auth": auth_version,
                },
            )
            await event(
                session,
                current,
                "COMMAND",
                command["id"],
                command["revision"] + 1,
                "ACCOUNT_SYNC_RUNNING",
                command["request_id"],
                {"attempt": command["attempt_count"] + 1},
            )
            return SyncClaim(
                self.tenant,
                command["id"],
                account["id"],
                claim_id,
                command["revision"] + 1,
                account["external_id"],
                configuration,
            ), True

    async def preflight(self, claim):
        async with self.sessions() as session, session.begin():
            account, command = await self.lock(session, claim.command, claim.account, write=False)
            if not claim_matches(command, claim):
                raise AccountReadFailure("ACCOUNT_SYNC_CLAIM_LOST")
            now = utc((await session.execute(text("SELECT UTC_TIMESTAMP(6)"))).scalar_one())
            if utc(command["claimed_at"]) + timedelta(seconds=LEASE_SECONDS) <= now:
                raise AccountReadFailure("ACCOUNT_SYNC_CLAIM_LOST")
            await self.verify(session, account, command)

    async def complete(self, claim, *, result=None, failure=None):
        async with self.sessions() as session, session.begin():
            account, command = await self.lock(session, claim.command, claim.account, write=True)
            if not claim_matches(command, claim):
                return False
            now = utc((await session.execute(text("SELECT UTC_TIMESTAMP(6)"))).scalar_one())
            if utc(command["claimed_at"]) + timedelta(seconds=LEASE_SECONDS) <= now:
                return False  # 交给有界租约回收，迟到结果不得落库。
            current = None
            try:
                current, _auth, _configuration = await self.verify(session, account, command)
            except AccountReadFailure as changed:
                failure = changed
            if failure is not None:
                if current is not None:
                    await invalidate_meta_read_source(
                        session, current, claim.configuration, failure.code, command["request_id"]
                    )
                due = retry_at(command["attempt_count"], now) if failure.retryable else None
                await self.transition(
                    session,
                    command,
                    "WAITING_RETRY" if due else "FAILED",
                    code=failure.code,
                    next_at=due,
                )
                return True
            try:
                value = metadata(result, claim.external_id, self.currencies)
                if (
                    value.currency != account["currency"]
                    or value.timezone_id != account["timezone_id"]
                ):
                    raise AccountReadFailure("ACCOUNT_METADATA_RECONCILIATION_REQUIRED")
                if value.observed_at > now or (
                    account["synced_at"] and value.observed_at <= utc(account["synced_at"])
                ):
                    raise AccountReadFailure("ACCOUNT_SYNC_OBSERVATION_STALE")
            except (OrbitError, AccountReadFailure) as error:
                await self.transition(session, command, "FAILED", code=error.code)
                return True
            details = _decode(account["details_json"]) | {
                "source_config_id": command["source_config_id"],
                "source_config_revision": command["source_config_revision"],
                "metadata_observed_at": value.observed_at.isoformat(
                    timespec="milliseconds"
                ).replace("+00:00", "Z"),
            }
            await session.execute(
                text(
                    "UPDATE orbit_ad_account SET name=:name,name_prefix=:prefix,"
                    "account_status=:status,auth_status=:auth,synced_at=:observed,"
                    "details_json=:details,revision=revision+1 "
                    "WHERE tenant_id=:tenant AND id=:id AND revision=:expected"
                ),
                {
                    "tenant": self.tenant,
                    "id": account["id"],
                    "expected": account["revision"],
                    "name": value.name,
                    "prefix": value.name[:191],
                    "status": value.account_status,
                    "auth": value.auth_status,
                    "observed": value.observed_at.replace(tzinfo=None),
                    "details": canonical(details),
                },
            )
            # 保留原金额观测/未知值和历史归属；元数据HTTP未返回金额，不能补零。
            await event(
                session,
                current,
                "ACCOUNT",
                account["id"],
                account["revision"] + 1,
                "ACCOUNT_METADATA_SYNCHRONIZED",
                command["request_id"],
                {
                    "command_id": command["id"],
                    "observed_at": details["metadata_observed_at"],
                    "source_config_id": command["source_config_id"],
                    "source_config_revision": command["source_config_revision"],
                },
            )
            await self.transition(session, command, "SUCCEEDED")
            return True

    async def run_once(self, *, limit=10):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise OrbitError(422, "FIELD_INVALID", "同步批量上限必须1至100")
        processed = recovered = 0
        for _ in range(limit):
            claim, consumed = await self.claim()
            if not consumed:
                break
            if claim is None:
                recovered += 1
                continue
            processed += 1
            try:
                reader = (
                    MetaAccountSourceReader(
                        claim.configuration, adapter_factory=self.meta_adapter_factory
                    )
                    if isinstance(claim.configuration, MetaAccountSource)
                    else self.platform_factory(claim.configuration)
                )
                reader.preflight = lambda captured=claim: self.preflight(captured)
                await reader.prepare((claim.external_id,))
                result = await reader.fetch_metadata(claim.external_id)
            except AccountReadFailure as failure:
                await self.complete(claim, failure=failure)
            else:
                await self.complete(claim, result=result)
        return {"processed": processed, "recovered": recovered}
