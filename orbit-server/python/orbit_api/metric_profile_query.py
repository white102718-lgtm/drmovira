"""指标配置原分页只读合同；新事务建立快照，目录共享不虚构目标Ownership。"""

import hashlib
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from orbit_api.authorization import require_business_access
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_contract import parse_model, uuid_field
from orbit_api.launch_execution_contract import MetricProfile
from orbit_api.metric_profile_contract import (
    MAX_REVISION,
    check_proof,
    parse_source_proof,
    unavailable,
)
from orbit_api.metric_profile_store import SOURCE_AVAILABLE, SOURCE_JOINS, fixture_boundary

CURSOR_PURPOSE = "METRIC_PROFILE_CURSOR_V1"
QUERY_FIELDS = {"q", "metric_profile_id", "cursor", "page_size"}


def parse_metric_profile_filters(raw):
    if not isinstance(raw, dict) or set(raw) - QUERY_FIELDS:
        raise OrbitError(400, "UNKNOWN_FIELD", "指标目录不接受未定义的筛选字段")
    size = raw.get("page_size", "50")
    if not isinstance(size, str) or size not in {"20", "50", "100", "200"}:
        raise OrbitError(422, "FIELD_INVALID", "指标分页数量无效", "/page_size")
    cursor = raw.get("cursor")
    if cursor is not None and (not isinstance(cursor, str) or not 1 <= len(cursor) <= 2048):
        raise OrbitError(422, "FIELD_INVALID", "指标游标长度无效", "/cursor")
    filters = {"page_size": int(size)}
    for field in ("q", "metric_profile_id"):
        value = raw.get(field, "")
        if value == "":
            filters[field] = ""
        else:
            filters[field] = uuid_field(value, (field,))
    return filters, cursor


def utc_text(value):
    if not isinstance(value, datetime):
        unavailable()
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    if value.utcoffset().total_seconds() != 0:
        unavailable()
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def cursor_time(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if utc_text(parsed) != value or parsed.tzinfo is None:
            raise ValueError
        return parsed
    except (ValueError, TypeError, AttributeError):
        raise OrbitError(400, "TOKEN_INVALID", "指标游标时间无效，请从首页加载") from None


def mysql_millisecond_instant(value):
    """MySQL DATETIME(3)默认四舍五入，500微秒进位，包含跨秒/日/年边界。"""
    if not isinstance(value, datetime):
        unavailable()
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    if value.utcoffset().total_seconds() != 0:
        unavailable()
    try:
        rounded = value + timedelta(microseconds=500)
    except OverflowError:
        unavailable()
    return rounded.replace(microsecond=rounded.microsecond // 1000 * 1000)


def validated_public_profile(row, *, isolated_fixture, now, historical=False):
    """数据库JSON/规范摘要/独立来源列须同时一致，不以列表隐藏坏行。"""
    try:
        value = (
            json.loads(row["payload_json"])
            if isinstance(row["payload_json"], str)
            else row["payload_json"]
        )
        profile = parse_model(canonical(value).encode(), MetricProfile)
        proof_doc = (
            json.loads(row["source_proof_json"])
            if isinstance(row["source_proof_json"], str)
            else row["source_proof_json"]
        )
        proof = parse_source_proof(proof_doc, row["source"])
        check_proof(proof, row["source"])
        observed = row["observed_at"]
        if not isinstance(observed, datetime) or observed.microsecond % 1000:
            unavailable()
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=UTC)
        if observed.utcoffset().total_seconds() != 0:
            unavailable()
        if (
            profile["id"] != row["id"]
            or profile["version"] != row["current_version"]
            or profile["source"] != row["source"]
            or hashlib.sha256(canonical(value).encode()).hexdigest() != row["payload_hash"]
            or proof.source_sha256 != row["source_sha256"]
            or proof.evidence_ref != row["evidence_ref"]
            or proof.source_config_id != row["source_config_id"]
            or proof.source_config_revision != row["source_config_revision"]
            or proof.source_connection_id != row.get("source_connection_id")
            or proof.source_connection_revision != row.get("source_connection_revision")
            or observed != mysql_millisecond_instant(proof.observed_at)
            or observed > now
        ):
            unavailable()
        if row["source"] == "FIXTURE":
            if not isolated_fixture or row["authority_kind"] != "ISOLATED_TEST":
                unavailable()
        elif row["source"] == "META":
            if row["authority_kind"] != "TRUSTED":
                unavailable()
            if historical:
                pass  # 历史候选已由完整发行收据及冻结归属过滤，不授予新采集权限。
            elif proof.source_connection_id is not None:
                if (
                    row.get("connection_id") != proof.source_connection_id
                    or row.get("connection_revision") != proof.source_connection_revision
                    or row.get("connection_status") != "ACTIVE"
                ):
                    unavailable()
            elif (
                row["config_section"] != "META_BM"
                or row["config_enabled"] != 1
                or row["config_revision"] != proof.source_config_revision
                or row["config_id"] != proof.source_config_id
            ):
                unavailable()
        else:
            unavailable()
        return profile
    except OrbitError as error:
        if error.status == 503:
            raise
        unavailable()
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError):
        unavailable()


class MetricProfileQuery:
    def __init__(self, tokens, *, isolated_fixture=False, historical=False):
        if type(isolated_fixture) is not bool:
            raise ValueError("隔离来源开关必须由可信构造器明确提供")
        if type(historical) is not bool:
            raise ValueError("历史查询必须由服务端明确指定")
        self.historical = historical
        self.tokens = tokens
        self.isolated_fixture = isolated_fixture

    async def page(self, session, actor, authorization, raw_filters):
        filters, cursor = parse_metric_profile_filters(raw_filters)
        if type(actor) is not int or actor < 1 or not isinstance(authorization, str):
            raise ValueError("指标查询需要可信当前会话身份")
        # RR旧事务已建立的快照不能与新clock搭配；禁止复用事务而不是猜测快照状态。
        if session.in_transaction():
            raise ValueError("指标分页必须使用空闲session和自有全新事务")
        async with session.begin():
            current = await require_business_access(session, actor, "monitor", "monitor.read")
            if self.isolated_fixture:
                await fixture_boundary(session)
            identity = (
                await session.execute(
                    text(
                        "SELECT auth_version FROM sys_identity_subject "
                        "WHERE user_id=:actor FOR SHARE"
                    ),
                    {"actor": actor},
                )
            ).scalar_one()
            scope = (
                await session.execute(
                    text(
                        "SELECT revision FROM orbit_directory_clock "
                        "WHERE tenant_id=:tenant FOR SHARE"
                    ),
                    {"tenant": current.tenant_id},
                )
            ).scalar_one_or_none()
            clock = (
                (
                    await session.execute(
                        text(
                            "SELECT revision,UTC_TIMESTAMP(3) AS now "
                            "FROM orbit_metric_profile_clock "
                            "WHERE tenant_id=:tenant FOR SHARE"
                        ),
                        {"tenant": current.tenant_id},
                    )
                )
                .mappings()
                .first()
            )
            if (
                type(identity) is not int
                or identity < 1
                or type(scope) is not int
                or not 1 <= scope <= MAX_REVISION
                or clock is None
                or type(clock["revision"]) is not int
                or not 1 <= clock["revision"] <= MAX_REVISION
            ):
                raise OrbitError(
                    503, "METRIC_PROFILE_INITIALIZATION_REQUIRED", "指标及授权目录尚未初始化"
                )
            now = clock["now"].replace(tzinfo=UTC)
            binding = hashlib.sha256(
                canonical(
                    [
                        "METRIC_PROFILE_PAGE_V1",
                        self.historical,
                        self.tokens.session_binding(authorization, actor, current.tenant_id),
                        actor,
                        current.tenant_id,
                        current.subject_id,
                        current.team_id,
                        current.data_role,
                        identity,
                        scope,
                        filters,
                    ]
                ).encode()
            ).hexdigest()
            after, after_version, as_of = "", "", utc_text(now)
            if cursor:
                claims = self.tokens.verify(CURSOR_PURPOSE, cursor)
                if (
                    type(claims.get("v")) is not int
                    or claims.get("v") != 1
                    or claims.get("scope") != binding
                ):
                    raise OrbitError(409, "SCOPE_CHANGED", "指标筛选或会话授权范围已变化")
                if (
                    type(claims.get("revision")) is not int
                    or claims.get("revision") != clock["revision"]
                ):
                    raise OrbitError(
                        409, "METRIC_PROFILE_CHANGED", "指标来源目录已变化，请从首页加载"
                    )
                after = uuid_field(claims.get("after"), ("cursor",))
                if self.historical:
                    after_version = claims.get("after_version")
                    if type(after_version) is not str or not 1 <= len(after_version) <= 64:
                        raise OrbitError(400, "TOKEN_INVALID", "历史版本游标无效")
                as_of = claims.get("as_of")
                if cursor_time(as_of) > now:
                    raise OrbitError(400, "TOKEN_INVALID", "指标游标时间无效")
            clauses = (
                [
                    "h.tenant_id=:tenant",
                    "(h.id>:after OR (h.id=:after AND v.version>:after_version))",
                ]
                if self.historical
                else ["h.tenant_id=:tenant", "h.state='ENABLED'", "h.id>:after"]
            )
            values = {
                "tenant": current.tenant_id,
                "after": after,
                "limit": filters["page_size"] + 1,
            }
            # 两个精确UUID独立AND，冲突严格取交集为空，不悄悄覆盖任何一个过滤器。
            for key in ("q", "metric_profile_id"):
                if filters[key]:
                    clauses.append("h.id=:" + key)
                    values[key] = filters[key]
            if self.historical:
                clauses.append(history_source_clause(current))
                values.update(
                    after_version=after_version,
                    subject=current.subject_id,
                    actor=current.actor_id,
                    as_of=cursor_time(as_of).replace(tzinfo=None),
                )
            else:
                clauses.append(SOURCE_AVAILABLE)
            # 首个普通InnoDB一致读在clock共享锁之后，绝不在这里反向锁来源配置。
            rows = (
                (
                    await session.execute(
                        text(
                            (
                                "SELECT h.id,v.version AS current_version,"
                                if self.historical
                                else "SELECT h.id,h.current_version,"
                            )
                            + "v.payload_json,v.payload_hash,v.source,"
                            "v.authority_kind,v.source_config_id,v.source_config_revision,v.sou"
                            "rce_connection_id,v.source_connection_revision,mc.id AS "
                            "connection_id,mc.revision AS connection_revision,mc.status AS "
                            "connection_status,v.source_sha256,"
                            "v.evidence_ref,v.observed_at,v.source_proof_json,c.id AS config_id,"
                            "c.enabled AS config_enabled,"
                            "c.section AS config_section,c.revision AS config_revision "
                            "FROM orbit_metric_profile_head h JOIN orbit_metric_profile_version v "
                            "ON v.tenant_id=h.tenant_id AND v.profile_id=h.id "
                            + ("" if self.historical else "AND v.version=h.current_version ")
                            + "LEFT JOIN orbit_system_configuration c ON c.tenant_id=v.tenant_id "
                            "AND c.id=v.source_config_id "
                            + SOURCE_JOINS
                            + " WHERE "
                            + " AND ".join(clauses)
                            + (
                                " ORDER BY h.id,v.version LIMIT :limit"
                                if self.historical
                                else " ORDER BY h.id LIMIT :limit"
                            )
                        ),
                        values,
                    )
                )
                .mappings()
                .all()
            )
            public = [
                validated_public_profile(
                    row, isolated_fixture=self.isolated_fixture, now=now, historical=self.historical
                )
                for row in rows
            ]
            size = filters["page_size"]
            token = (
                self.tokens.issue(
                    CURSOR_PURPOSE,
                    {
                        "v": 1,
                        "scope": binding,
                        "revision": clock["revision"],
                        "after": rows[size - 1]["id"],
                        **(
                            {"after_version": rows[size - 1]["current_version"]}
                            if self.historical
                            else {}
                        ),
                        "as_of": as_of,
                    },
                )
                if len(rows) > size
                else None
            )
            return {
                "items": public[:size],
                "next_cursor": token,
                "data_as_of": as_of,
                "scope_version": scope,
            }


def history_source_clause(current):
    """完整Meta发行且有当前可见冻结单元，连接断开不撤销已保存事实。"""
    visible = "hc.owner_user_id=:subject"
    if current.data_role == "SUPER_ADMIN":
        visible = "1=1"
    elif current.data_role == "TEAM_ADMIN":
        visible += (
            " OR EXISTS(SELECT 1 FROM orbit_business_team_manager tm "
            "WHERE tm.tenant_id=hc.tenant_id AND tm.team_id=hc.owner_team_id "
            "AND tm.manager_user_id=:actor AND tm.enabled=1)"
        )
    return (
        "v.source='META' AND v.authority_kind='TRUSTED' AND EXISTS("
        "SELECT 1 FROM orbit_metric_publication hp "
        "JOIN orbit_meta_metric_publication_receipt hr ON hr.tenant_id=hp.tenant_id AND "
        "hr.publication_id=hp.id "
        "JOIN orbit_meta_metric_job hj ON hj.tenant_id=hr.tenant_id AND hj.id=hr.job_id AND "
        "hj.publication_id=hp.id "
        "JOIN orbit_metric_capture_cell hc ON hc.tenant_id=hp.tenant_id AND "
        "hc.publication_id=hp.id "
        "WHERE hp.tenant_id=v.tenant_id AND hp.profile_id=v.profile_id AND "
        "hp.profile_version=v.version "
        "AND hp.profile_hash=v.payload_hash AND hp.authority_kind='TRUSTED' AND "
        "hp.state='PUBLISHED' "
        "AND hj.state='PUBLISHED' AND hp.published_at<=:as_of AND (" + visible + "))"
    )
