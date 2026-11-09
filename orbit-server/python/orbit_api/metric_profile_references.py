"""草稿指标资料精确冻结；不猜参数适配版本，不编译执行，不写计划或幂等记录。"""

from datetime import UTC, datetime

from sqlalchemy import bindparam, text

from orbit_api.authorization import BusinessContext, require_business_access
from orbit_api.errors import OrbitError
from orbit_api.launch_contract import MAX_NODES, uuid_field
from orbit_api.metric_profile_contract import MAX_REVISION, unavailable
from orbit_api.metric_profile_query import validated_public_profile
from orbit_api.metric_profile_store import fixture_boundary

BATCH_SIZE = 200


def collect_metric_profile_ids(campaigns):
    """仅从原adset字段收集，重复引用复用同一版本，不扩展PlanWrite字段。"""
    result, nodes = set(), 0
    for ci, campaign in enumerate(campaigns):
        for si, adset in enumerate(campaign["adsets"]):
            nodes += 1
            if nodes > MAX_NODES:
                raise OrbitError(422, "PLAN_NODE_LIMIT", "原计划节点预算已超限", "/campaigns")
            identifier = adset.get("metric_profile_id")
            if identifier is not None:
                result.add(
                    uuid_field(identifier, ("campaigns", ci, "adsets", si, "metric_profile_id"))
                )
    return sorted(result)


async def _rows(session, statement, values, *, identifiers=None):
    query = text(statement)
    if identifiers is not None:
        query = query.bindparams(bindparam("ids", expanding=True))
        values = values | {"ids": identifiers}
    return (await session.execute(query, values)).mappings().all()


def _changed():
    raise OrbitError(409, "METRIC_PROFILE_SOURCE_CHANGED", "指标来源已变化，请重新加载后保存")


async def _owner_identity(session, current, owner_actor, ownership):
    if type(owner_actor) is not int or owner_actor < 1:
        raise ValueError("目标原生身份必须来自服务端归属核验")
    if not isinstance(ownership, dict) or set(ownership) != {"owner_user_id", "owner_team_id"}:
        raise ValueError("需要原计划严格归属对象")
    owner_subject = uuid_field(ownership["owner_user_id"], ("ownership", "owner_user_id"))
    owner_team = uuid_field(ownership["owner_team_id"], ("ownership", "owner_team_id"))
    rows = await _rows(
        session,
        "SELECT s.tenant_id,s.data_role,b.id AS subject_id,b.team_id "
        "FROM orbit_user_scope s JOIN sys_user u ON u.user_id=s.user_id "
        "AND u.status='0' AND u.del_flag='0' "
        "JOIN sys_identity_subject i ON i.user_id=u.user_id AND i.auth_version>=1 "
        "JOIN orbit_tenant t ON t.id=s.tenant_id AND t.enabled=1 "
        "JOIN orbit_business_user b ON b.tenant_id=s.tenant_id AND b.user_id=s.user_id "
        "AND b.enabled=1 AND b.invited=0 "
        "JOIN orbit_business_team bt ON bt.tenant_id=b.tenant_id "
        "AND bt.id=b.team_id AND bt.enabled=1 "
        "WHERE s.user_id=:owner AND s.enabled=1 FOR SHARE",
        {"owner": owner_actor},
    )
    if (
        len(rows) != 1
        or rows[0]["tenant_id"] != current.tenant_id
        or rows[0]["subject_id"] != owner_subject
        or rows[0]["team_id"] != owner_team
        or rows[0]["data_role"] not in {"USER", "TEAM_ADMIN", "SUPER_ADMIN"}
    ):
        raise OrbitError(404, "METRIC_PROFILE_UNAVAILABLE", "目标拥有者当前身份或归属不可用")


async def resolve_metric_profile_dependencies(
    session,
    current,
    owner_actor,
    ownership,
    profile_ids,
    *,
    permission,
    isolated_fixture=False,
):
    """外层事务：来源配置全局UUID锁→metric clock→有序head/version；之后才由调用方锁计划。

    root调用方负责原动作与对象归属范围，函数仍复核实时caller身份、owner当前身份。
    templates.create/edit保留在原launch菜单中，不叠加计划create/edit权限。
    成功旧幂等键由调用方先重放原结果，不能再次进入本函数重绑或阻断旧成功响应。
    不接收前端version/adapter，不在clock后补锁改变后的来源；不自行commit。
    """
    if permission not in {"launch.create", "launch.edit", "templates.create", "templates.edit"}:
        raise ValueError("资料引用必须显式沿用原计划或模板create/edit动作")
    if not isinstance(current, BusinessContext) or not session.in_transaction():
        raise ValueError("资料冻结需要可信当前context及调用者外层事务")
    if type(isolated_fixture) is not bool:
        raise ValueError("隔离来源开关必须由可信构造器提供")
    if not isinstance(profile_ids, (list, tuple)):
        raise ValueError("指标ID必须来自原adset字段收集")
    if len(profile_ids) > MAX_NODES:
        raise OrbitError(422, "PLAN_NODE_LIMIT", "原计划节点预算已超限", "/campaigns")
    identifiers = sorted({uuid_field(value, ("metric_profile_id",)) for value in profile_ids})
    if isolated_fixture:
        # 即使没有引用也检查显式fixture开关，绝无空集合绕过生产边界。
        await fixture_boundary(session)
    if not identifiers:
        return {"metric_profiles": {}}
    caller = await require_business_access(session, current.actor_id, "launch", permission)
    if caller != current:
        raise OrbitError(403, "PERMISSION_DENIED", "投放动作或授权范围已变化")
    await _owner_identity(session, current, owner_actor, ownership)
    params = {"tenant": current.tenant_id}
    metadata = {}
    for offset in range(0, len(identifiers), BATCH_SIZE):
        batch = identifiers[offset : offset + BATCH_SIZE]
        rows = await _rows(
            session,
            "SELECT h.id,h.current_version,v.source,v.source_config_id,v.source_config_revision "
            "FROM orbit_metric_profile_head h JOIN orbit_metric_profile_version v "
            "ON v.tenant_id=h.tenant_id AND v.profile_id=h.id AND v.version=h.current_version "
            "WHERE h.tenant_id=:tenant AND h.id IN :ids AND h.state='ENABLED' ORDER BY h.id",
            params,
            identifiers=batch,
        )
        if {row["id"] for row in rows} != set(batch):
            raise OrbitError(404, "METRIC_PROFILE_UNAVAILABLE", "指标资料不存在或已停用")
        metadata.update({row["id"]: dict(row) for row in rows})
    sources = set()
    for row in metadata.values():
        if row["source"] == "META":
            try:
                sources.add(uuid_field(row["source_config_id"], ("metric_profile_source",)))
            except OrbitError:
                unavailable()
        elif row["source"] != "FIXTURE" or not isolated_fixture:
            unavailable()
    sources = sorted(sources)
    configurations = {}
    for offset in range(0, len(sources), BATCH_SIZE):
        rows = await _rows(
            session,
            "SELECT id,section,enabled,revision FROM orbit_system_configuration "
            "FORCE INDEX(PRIMARY) "
            "WHERE tenant_id=:tenant AND id IN :ids ORDER BY id FOR SHARE",
            params,
            identifiers=sources[offset : offset + BATCH_SIZE],
        )
        configurations.update({row["id"]: dict(row) for row in rows})
    for row in metadata.values():
        if row["source"] == "META":
            source = configurations.get(row["source_config_id"])
            if (
                source is None
                or source["section"] != "META_BM"
                or source["enabled"] != 1
                or source["revision"] != row["source_config_revision"]
            ):
                _changed()
    clock = (
        (
            await session.execute(
                text(
                    "SELECT revision,UTC_TIMESTAMP(3) AS now FROM orbit_metric_profile_clock "
                    "WHERE tenant_id=:tenant FOR SHARE"
                ),
                params,
            )
        )
        .mappings()
        .first()
    )
    if (
        clock is None
        or type(clock["revision"]) is not int
        or not 1 <= clock["revision"] <= MAX_REVISION
    ):
        raise OrbitError(503, "METRIC_PROFILE_INITIALIZATION_REQUIRED", "指标注册表尚未初始化")
    if not isinstance(clock["now"], datetime):
        unavailable()
    now = clock["now"].replace(tzinfo=UTC)
    dependencies = {}
    for offset in range(0, len(identifiers), BATCH_SIZE):
        batch = identifiers[offset : offset + BATCH_SIZE]
        # 固定驱动主键范围并有序读取；不JOIN配置，以免变更来源在clock后被隐式补锁。
        rows = await _rows(
            session,
            "SELECT h.id,h.current_version,h.revision AS head_revision,h.state,v.payload_json,"
            "v.payload_hash,v.source,v.authority_kind,v.source_config_id,v.source_config_revision,"
            "v.source_sha256,v.evidence_ref,v.observed_at,v.source_proof_json "
            "FROM orbit_metric_profile_head h FORCE INDEX(PRIMARY) "
            "STRAIGHT_JOIN orbit_metric_profile_version v FORCE INDEX(PRIMARY) "
            "ON v.tenant_id=h.tenant_id AND v.profile_id=h.id AND v.version=h.current_version "
            "WHERE h.tenant_id=:tenant AND h.id IN :ids ORDER BY h.id FOR SHARE",
            params,
            identifiers=batch,
        )
        if {row["id"] for row in rows} != set(batch):
            _changed()
        for raw in rows:
            row = dict(raw)
            if row["state"] != "ENABLED" or any(
                row[field] != metadata[row["id"]][field]
                for field in (
                    "current_version",
                    "source",
                    "source_config_id",
                    "source_config_revision",
                )
            ):
                _changed()
            if (
                type(row["head_revision"]) is not int
                or not 1 <= row["head_revision"] <= MAX_REVISION
            ):
                unavailable()
            source = configurations.get(row["source_config_id"], {})
            row.update(
                config_id=source.get("id"),
                config_section=source.get("section"),
                config_enabled=source.get("enabled"),
                config_revision=source.get("revision"),
            )
            profile = validated_public_profile(row, isolated_fixture=isolated_fixture, now=now)
            dependencies[row["id"]] = {
                "version": profile["version"],
                "head_revision": row["head_revision"],
                "profile_hash": row["payload_hash"],
                "source_sha256": row["source_sha256"],
                "source_config_id": row["source_config_id"],
                "source_config_revision": row["source_config_revision"],
            }
    return {"metric_profiles": dependencies, "metric_profile_clock": clock["revision"]}
