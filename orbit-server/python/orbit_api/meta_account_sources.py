"""账户导入/同步的显式Meta连接来源；失效不猜测或回退其他凭据。"""

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text

from orbit_api.account_access import event
from orbit_api.account_platform import AccountReadFailure
from orbit_api.authorization import require_business_access
from orbit_api.configuration_store import _decode
from orbit_api.meta_read_adapter import GraphReadTransport, MetaReadAdapter
from orbit_api.meta_read_contract import MetaReadConfiguration, MetaReadFailure
from orbit_api.reference_access import managed_teams, readable


@dataclass(frozen=True, repr=False)
class MetaAccountSource:
    configuration: MetaReadConfiguration
    kind: str
    business_id: str | None
    import_selection: tuple[int, str | None] | None = None
    discovered: bool = False
    principal_id: str | None = None


async def optional_table(session, table):
    # 旧隔离迁移范围不包含新模块；查询不存在时不能吞掉真实数据库故障。
    return bool(
        (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() "
                    "AND TABLE_NAME=:table"
                ),
                {"table": table},
            )
        ).scalar_one()
    )


async def invalidate_meta_read_source(session, current, source, code, request_id):
    """已复验领取者的实际190认证失败；权限拒绝不代表Token失效。

    调用者须已锁账户时钟并复验当前导入/同步权限及领取栅栏；同事务失败状态与审计。
    """
    if code != "META_AUTH_FAILED" or not isinstance(source, MetaAccountSource):
        return False
    if not session.in_transaction():
        raise ValueError("来源失效必须与只读任务回写同事务")
    configuration = source.configuration
    params = {
        "tenant": current.tenant_id,
        "id": configuration.source_config_id,
        "revision": configuration.source_config_revision,
    }
    result = await session.execute(
        text(
            "UPDATE orbit_meta_connection SET status='REAUTH_REQUIRED',token_envelope=NULL,"
            "revision=revision+1,updated_at=UTC_TIMESTAMP(3) WHERE tenant_id=:tenant AND id=:id "
            "AND revision=:revision AND status='ACTIVE'"
        ),
        params,
    )
    if result.rowcount != 1:
        return False
    await event(
        session,
        current,
        "META_CONNECTION",
        configuration.source_config_id,
        configuration.source_config_revision + 1,
        "META_AUTHORIZATION_EXPIRED",
        request_id,
        {},
    )
    return True


async def import_source(session, tenant, batch):
    if not await optional_table(session, "orbit_meta_import_source"):
        return None
    return (
        (
            await session.execute(
                text(
                    "SELECT * FROM orbit_meta_import_source WHERE tenant_id=:tenant "
                    "AND batch_id=:batch FOR SHARE"
                ),
                {"tenant": tenant, "batch": batch},
            )
        )
        .mappings()
        .first()
    )


async def account_source(session, tenant, account):
    if not await optional_table(session, "orbit_meta_account_source"):
        return None
    return (
        (
            await session.execute(
                text(
                    "SELECT * FROM orbit_meta_account_source WHERE tenant_id=:tenant "
                    "AND account_id=:account FOR SHARE"
                ),
                {"tenant": tenant, "account": account},
            )
        )
        .mappings()
        .first()
    )


def source_marker(row):
    return {key: row[key] for key in ("connection_id", "connection_revision", "revision")}


async def load_sync_source(session, cipher, tenant, account, command, graph_version):
    """显式关联和受理时冻结快照必须完全一致；删关联或切换来源使旧任务失效。"""
    selected = await account_source(session, tenant, account)
    frozen = _decode(command["source_json"]).get("meta_connection_source")
    if selected is None and frozen is None:
        return None
    if (
        selected is None
        or frozen != source_marker(selected)
        or command["source_config_id"] != selected["connection_id"]
        or command["source_config_revision"] != selected["connection_revision"]
    ):
        raise AccountReadFailure("ACCOUNT_SYNC_SOURCE_CHANGED")
    return await load_connection(
        session,
        cipher,
        tenant,
        selected["connection_id"],
        selected["connection_revision"],
        graph_version,
    )


def _utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def require_connection(row, identifier, revision):
    now = datetime.now(UTC)
    if (
        not row
        or row["id"] != identifier
        or row["revision"] != revision
        or row["status"] != "ACTIVE"
        or row["kind"] not in {"LOGIN", "BM"}
        or not row["token_envelope"]
        or any(
            row[key] is not None and _utc(row[key]) <= now
            for key in ("expires_at", "data_access_expires_at")
        )
        or not set(_decode(row["scopes_json"])) & {"ads_read", "ads_management"}
    ):
        raise AccountReadFailure("META_CONNECTION_SOURCE_CHANGED")


async def connection_row(session, tenant, identifier, revision):
    row = (
        (
            await session.execute(
                text(
                    "SELECT * FROM orbit_meta_connection "
                    "WHERE tenant_id=:tenant AND id=:id FOR SHARE"
                ),
                {"tenant": tenant, "id": identifier},
            )
        )
        .mappings()
        .first()
    )
    require_connection(row, identifier, revision)
    if row.get("app_configuration_id"):
        config = (
            (
                await session.execute(
                    text(
                        "SELECT revision,enabled,section,settings_json FROM "
                        "orbit_system_configuration WHERE tenant_id=:tenant AND id=:id FOR SHARE"
                    ),
                    {"tenant": tenant, "id": row["app_configuration_id"]},
                )
            )
            .mappings()
            .first()
        )
        if (
            config is None
            or not config["enabled"]
            or config["section"] != "META_APP"
            or config["revision"] != row["app_configuration_revision"]
            or _decode(config["settings_json"]).get("appId") != row["app_id"]
        ):
            raise AccountReadFailure("META_CONNECTION_SOURCE_CHANGED")
    return row


async def load_connection(session, cipher, tenant, identifier, revision, graph_version):
    """每个真实HTTP前和回写前复验版本/到期/BM原配置；Token只在私有对象中流转。"""
    row = await connection_row(session, tenant, identifier, revision)
    business = None
    if row["kind"] == "BM":
        configuration = (
            (
                await session.execute(
                    text(
                        "SELECT id,revision,settings_json FROM orbit_system_configuration "
                        "WHERE tenant_id=:tenant AND id=:id AND revision=:revision "
                        "AND section='META_BM' "
                        "AND enabled=1 AND verification_status='READ_VERIFIED' FOR SHARE"
                    ),
                    {
                        "tenant": tenant,
                        "id": row["configuration_id"],
                        "revision": row["configuration_revision"],
                    },
                )
            )
            .mappings()
            .first()
        )
        if configuration is None or configuration["revision"] != row["configuration_revision"]:
            raise AccountReadFailure("META_CONNECTION_SOURCE_CHANGED")
        settings = _decode(configuration["settings_json"])
        business = settings.get("businessId")
        if not isinstance(business, str) or re.fullmatch("[0-9]{1,64}", business) is None:
            raise AccountReadFailure("META_CONNECTION_SOURCE_CHANGED")
    try:
        if not cipher.ready:
            raise AccountReadFailure("META_CONNECTION_SOURCE_UNAVAILABLE")
        token = cipher.decrypt_internal(row["token_envelope"], tenant, identifier, "meta_token")
        configuration = MetaReadConfiguration(identifier, revision, graph_version, token)
    except AccountReadFailure:
        raise
    except Exception:
        raise AccountReadFailure("META_CONNECTION_SOURCE_UNAVAILABLE") from None
    return MetaAccountSource(configuration, row["kind"], business, principal_id=row["principal_id"])


async def validate_import_channel(session, current, channel_id):
    """复用账户渠道写入的动作许可、当前渠道范围与启用条件；不是导入绕过分配权限。"""
    if channel_id is None:
        return
    authorized = await require_business_access(
        session, current.actor_id, "accounts", "accounts.assign", acting_subject=False
    )
    if authorized.tenant_id != current.tenant_id or authorized.subject_id != current.subject_id:
        raise AccountReadFailure("ACCOUNT_IMPORT_CHANNEL_CHANGED")
    row = (
        (
            await session.execute(
                text("SELECT * FROM orbit_channel WHERE tenant_id=:tenant AND id=:id FOR SHARE"),
                {"tenant": current.tenant_id, "id": channel_id},
            )
        )
        .mappings()
        .first()
    )
    if (
        row is None
        or row["status"] != "ENABLED"
        or not readable(
            authorized,
            await managed_teams(session, authorized),
            _decode(row["value_json"])["ownership"],
        )
    ):
        raise AccountReadFailure("ACCOUNT_IMPORT_CHANNEL_CHANGED")


async def attach_import_source(session, current, batch_id, account_id, request_id):
    """仅在新建账户同事务调用；旧账户重导入绝不覆盖来源、归属或当前渠道。"""
    selected = await import_source(session, current.tenant_id, batch_id)
    if selected is None:
        return
    await connection_row(
        session, current.tenant_id, selected["connection_id"], selected["connection_revision"]
    )
    await validate_import_channel(session, current, selected["channel_id"])
    params = {
        "tenant": current.tenant_id,
        "account": account_id,
        "connection": selected["connection_id"],
        "version": selected["connection_revision"],
        "channel": selected["channel_id"],
    }
    await session.execute(
        text(
            "INSERT INTO orbit_meta_account_source "
            "(tenant_id,account_id,connection_id,connection_revision,revision) "
            "VALUES(:tenant,:account,:connection,:version,1)"
        ),
        params,
    )
    if selected["channel_id"] is not None:
        await session.execute(
            text(
                "INSERT INTO orbit_account_current_channel"
                "(tenant_id,account_id,channel_id,updated_at) "
                "VALUES(:tenant,:account,:channel,UTC_TIMESTAMP(3))"
            ),
            params,
        )
    await event(
        session,
        current,
        "META_ACCOUNT_SOURCE",
        account_id,
        1,
        "META_SOURCE_BOUND",
        request_id,
        {
            "connection_id": selected["connection_id"],
            "connection_revision": selected["connection_revision"],
            "channel_id": selected["channel_id"],
        },
    )


class MetaAccountSourceReader:
    """适配原Worker prepare/fetch_metadata，完整可访问范围之后才允许取元数据。"""

    def __init__(self, source, *, adapter_factory=None):
        self.source = source
        self.preflight = None
        self.authorized = None
        self.guard_failure = None
        if adapter_factory is None:
            reader = self

            class GuardedTransport:
                async def request(self, *args, **kwargs):
                    if reader.preflight is not None:
                        try:
                            await reader.preflight()
                        except AccountReadFailure as error:
                            # 传输层只识别Meta固定错误；保留原授权拒绝且禁止其网络重试。
                            reader.guard_failure = error
                            raise MetaReadFailure("META_READ_FORBIDDEN") from None
                    return await GraphReadTransport().request(*args, **kwargs)

            self.adapter = MetaReadAdapter(source.configuration, transport=GuardedTransport())
        else:
            self.adapter = adapter_factory(source.configuration)

    async def prepare(self, identifiers):
        self.authorized = None
        self.guard_failure = None
        wanted = set(identifiers)
        if not 1 <= len(wanted) <= 500 or any(
            not isinstance(x, str) or not re.fullmatch("[0-9]{1,64}", x) for x in wanted
        ):
            raise AccountReadFailure("ACCOUNT_PLATFORM_REQUEST_REJECTED")
        if self.source.discovered:
            # 服务端已将发现页与批次原子持久化；每次account读取仍复验连接及当前平台权限。
            self.authorized = frozenset(wanted)
            return
        matched = set()
        edges = ("me",) if self.source.kind == "LOGIN" else ("owned", "client")
        try:
            async with asyncio.timeout(60):
                for edge in edges:
                    checkpoint = None
                    for _ in range(50):
                        if self.preflight is not None:
                            await self.preflight()
                        page = await self.adapter.accounts_page(
                            edge=edge, business_id=self.source.business_id, checkpoint=checkpoint
                        )
                        matched.update(
                            item["account_id"]
                            for item in page.items
                            if item["account_id"] in wanted
                        )
                        if page.complete:
                            break
                        if page.checkpoint is None:
                            raise AccountReadFailure("ACCOUNT_PLATFORM_SCOPE_INCOMPLETE")
                        checkpoint = page.checkpoint
                    else:
                        raise AccountReadFailure("ACCOUNT_PLATFORM_SCOPE_INCOMPLETE")
        except MetaReadFailure as error:
            if self.guard_failure is not None:
                raise self.guard_failure from None
            raise AccountReadFailure(error.code, retryable=error.retryable) from None
        except TimeoutError:
            raise AccountReadFailure("ACCOUNT_PLATFORM_READ_UNCERTAIN", retryable=True) from None
        self.authorized = frozenset(matched)

    async def fetch_metadata(self, external_id):
        self.guard_failure = None
        if self.authorized is None or external_id not in self.authorized:
            raise AccountReadFailure("ACCOUNT_PLATFORM_FORBIDDEN")
        try:
            if self.preflight is not None:
                await self.preflight()
            value = await self.adapter.account(external_id)
            if hasattr(self.adapter, "account_extras"):
                extras, principal = await self.adapter.account_extras(
                    external_id, principal=self.source.kind == "LOGIN"
                )
                if self.guard_failure is not None:
                    raise self.guard_failure
                if (
                    principal is not None
                    and self.source.principal_id is not None
                    and principal["id"] != self.source.principal_id
                ):
                    raise AccountReadFailure("META_ACCOUNT_MISMATCH")
                from orbit_api.meta_account_enrichment import business_managers, observations

                managers = business_managers(extras)
                enriched = observations(value | extras, datetime.now(UTC), principal=principal)
            else:
                enriched = {}
                managers = None
        except MetaReadFailure as error:
            if self.guard_failure is not None:
                raise self.guard_failure from None
            raise AccountReadFailure(error.code, retryable=error.retryable) from None
        return {
            **({"observations": enriched, "business_managers": managers} if enriched else {}),
            "external_id": value["account_id"],
            "name": value["name"],
            "currency": value["currency"],
            "timezone_id": value["timezone_name"],
            "account_status": "ACTIVE"
            if value["account_status"] == "1"
            else "DISABLED"
            if value["account_status"] == "2"
            else "UNKNOWN",
            "auth_status": "AUTHORIZED",
            "observed_at": datetime.now(UTC),
        }

    async def fetch_daily_spend(self, external_id, currency, timezone):
        """仅同步调用，复用相同授权连接、逐HTTP门禁与完整分页。"""
        self.guard_failure = None
        if self.authorized is None or external_id not in self.authorized:
            raise AccountReadFailure("ACCOUNT_PLATFORM_FORBIDDEN")
        from orbit_api.meta_account_daily_spend import read_daily_spend

        try:
            facts = await read_daily_spend(self.adapter, external_id, currency, timezone)
        except MetaReadFailure as error:
            if self.guard_failure is not None:
                raise self.guard_failure from None
            if error.code in {"META_READ_FORBIDDEN", "META_READ_REJECTED"}:
                return {
                    "facts": [],
                    "reason_code": "NOT_AUTHORIZED"
                    if error.code == "META_READ_FORBIDDEN"
                    else "READ_REJECTED",
                }
            raise AccountReadFailure(error.code, retryable=error.retryable) from None
        return {"facts": facts, "reason_code": None if facts else "NOT_PROVIDED"}
