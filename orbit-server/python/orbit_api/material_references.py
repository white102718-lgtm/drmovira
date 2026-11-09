"""计划/任务内部素材批量交集与活跃引用；调用者持外层事务，不在本模块提交。"""

import re
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import bindparam, text

from orbit_api.authorization import BusinessContext, require_business_access
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.identity_contract import _uuid
from orbit_api.material_security import clean_scan_ids
from orbit_api.material_store import one
from orbit_api.material_worker import MaterialWorker

MAX_REVISION = 9007199254740991
SAFE_COLUMNS = """id,revision,name,owner_user_id,owner_team_id,kind,state,sha256,mime,
byte_size,width_px,height_px,duration_seconds,physical_cleanup_state"""


def _identifier(value, pointer):
    if not isinstance(value, str):
        raise OrbitError(422, "FIELD_INVALID", "标识必须为UUID字符串", pointer)
    return _uuid(value, pointer)


def normalize_selection(ids, expected_revisions=None, expected_sha256=None):
    if not isinstance(ids, (list, tuple)) or not 1 <= len(ids) <= 200:
        raise OrbitError(422, "FIELD_INVALID", "内部素材批量必须1至200项", "/asset_ids")
    normalized = sorted({_identifier(value, "/asset_ids") for value in ids})
    for mapping, field in (
        (expected_revisions, "expected_revisions"),
        (expected_sha256, "expected_sha256"),
    ):
        if mapping is not None and (
            not isinstance(mapping, dict) or set(mapping) != set(normalized)
        ):
            raise OrbitError(422, "FIELD_INVALID", "素材冻结条件必须完整对应当前批次", "/" + field)
    if expected_revisions is not None:
        for revision in expected_revisions.values():
            if type(revision) is not int or not 1 <= revision <= MAX_REVISION:
                raise OrbitError(422, "FIELD_INVALID", "素材冻结版本无效", "/expected_revisions")
    if expected_sha256 is not None:
        for sha in expected_sha256.values():
            if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
                raise OrbitError(422, "FIELD_INVALID", "素材冻结摘要无效", "/expected_sha256")
    return normalized


def _require_transaction(session):
    if not session.in_transaction():
        raise ValueError("素材内部接口必须由调用者开启并持有同一外层事务")


async def _managed(session, context):
    if context.data_role != "TEAM_ADMIN":
        return ()
    values = (
        (
            await session.execute(
                text("""SELECT m.team_id FROM orbit_business_team_manager m
        JOIN orbit_business_team t ON t.tenant_id=m.tenant_id AND t.id=m.team_id AND t.enabled=1
        WHERE m.tenant_id=:tenant AND m.manager_user_id=:actor AND m.enabled=1
        ORDER BY m.team_id FOR SHARE"""),
                {"tenant": context.tenant_id, "actor": context.actor_id},
            )
        )
        .mappings()
        .all()
    )
    return tuple(row["team_id"] for row in values)


def _readable(row, context, teams):
    return (
        context.data_role == "SUPER_ADMIN"
        or row["owner_user_id"] == context.subject_id
        or (context.data_role == "TEAM_ADMIN" and row["owner_team_id"] in teams)
    )


async def _contexts(session, context, owner_user_id, owner_team_id):
    if not isinstance(context, BusinessContext):
        raise ValueError("必须传入服务端实时授权上下文")
    caller = await require_business_access(session, context.actor_id, "assets", "assets.read")
    if caller.tenant_id != context.tenant_id or caller.subject_id != context.subject_id:
        raise OrbitError(403, "PERMISSION_DENIED", "当前素材授权上下文已变化")
    owner_user_id = _identifier(owner_user_id, "/owner_user_id")
    owner_team_id = _identifier(owner_team_id, "/owner_team_id")
    owner = await one(
        session,
        """SELECT user_id FROM orbit_business_user WHERE tenant_id=:tenant
        AND id=:owner AND team_id=:team AND enabled=1 AND invited=0 FOR SHARE""",
        {"tenant": caller.tenant_id, "owner": owner_user_id, "team": owner_team_id},
    )
    if owner is None:
        raise OrbitError(404, "NOT_FOUND", "目标拥有者不可用于素材引用")
    try:
        target = await require_business_access(
            session, owner["user_id"], "assets", "assets.read", acting_subject=False
        )
    except OrbitError as error:
        if error.status == 403:
            raise OrbitError(404, "NOT_FOUND", "目标拥有者不可读取素材") from None
        raise
    if (
        target.tenant_id != caller.tenant_id
        or target.subject_id != owner_user_id
        or target.team_id != owner_team_id
    ):
        raise OrbitError(404, "NOT_FOUND", "目标拥有者范围已变化")
    return caller, target, await _managed(session, caller), await _managed(session, target)


async def require_allocation_assets(
    session,
    context,
    owner_user_id,
    owner_team_id,
    ids,
    expected_revisions=None,
    expected_sha256=None,
):
    """全批可用才返回；pool>200须先全量排序后分块，同事务全局升序持锁。"""
    _require_transaction(session)
    identifiers = normalize_selection(ids, expected_revisions, expected_sha256)
    caller, target, caller_teams, target_teams = await _contexts(
        session, context, owner_user_id, owner_team_id
    )
    await MaterialWorker.lock_clock(session, caller.tenant_id)
    transaction = session.sync_session.get_transaction()
    prior = session.info.get("orbit_material_batch_locks")
    locked = set(prior[1]) if prior and prior[0] is transaction else set()
    new_ids = set(identifiers) - locked
    if new_ids and locked and min(new_ids) < max(locked):
        raise ValueError("跨批素材必须按全局UUID升序首次加锁，不能逆序分块")
    statement = text(
        f"SELECT {SAFE_COLUMNS} FROM orbit_material_asset "
        "WHERE tenant_id=:tenant AND id IN :ids ORDER BY id FOR UPDATE"
    ).bindparams(bindparam("ids", expanding=True))
    values = (
        (await session.execute(statement, {"tenant": caller.tenant_id, "ids": identifiers}))
        .mappings()
        .all()
    )
    records = {row["id"]: row for row in values}
    # 不可见与不存在统一404，任何失败都不返回部分可用映射。
    for identifier in identifiers:
        row = records.get(identifier)
        if (
            row is None
            or not _readable(row, caller, caller_teams)
            or not _readable(row, target, target_teams)
        ):
            raise OrbitError(
                404,
                "MATERIAL_REFERENCE_UNAVAILABLE",
                "素材清单含缺失或当前双方不可读项",
                "/asset_ids",
            )
    verified = await clean_scan_ids(session, caller.tenant_id, identifiers)
    result = {}
    for identifier in identifiers:
        row = records[identifier]
        if row["owner_team_id"] != owner_team_id:
            raise OrbitError(
                422, "REFERENCE_TEAM_MISMATCH", "素材不能跨目标计划团队引用", "/asset_ids"
            )
        if row["state"] != "READY" or row["physical_cleanup_state"] != "LIVE":
            raise OrbitError(
                409, "MATERIAL_NOT_READY", "素材尚不可分配或已进入物理回收", "/asset_ids"
            )
        if expected_revisions is not None and row["revision"] != expected_revisions[identifier]:
            raise OrbitError(409, "REVISION_CONFLICT", "素材版本已变化", "/asset_ids")
        if expected_sha256 is not None and row["sha256"] != expected_sha256[identifier]:
            raise OrbitError(
                409, "MATERIAL_HASH_CONFLICT", "素材文件摘要与冻结清单不一致", "/asset_ids"
            )
        result[identifier] = {
            "id": identifier,
            "revision": row["revision"],
            "name": row["name"],
            "owner_user_id": row["owner_user_id"],
            "owner_team_id": row["owner_team_id"],
            "kind": row["kind"],
            "state": row["state"],
            "sha256": row["sha256"],
            "mime": row["mime"],
            "size": row["byte_size"],
            "width": row["width_px"],
            "height": row["height_px"],
            "duration": format(row["duration_seconds"], "f")
            if row["duration_seconds"] is not None
            else None,
            "physical_cleanup_state": row["physical_cleanup_state"],
            # 旧READY不继承为扫描通过；当前DONE任务必须有完整同对象CLEAN证据。
            "antivirus_status": "CLEAN" if identifier in verified else "UNVERIFIED",
            "execution_eligible": identifier in verified,
        }
    session.info["orbit_material_batch_locks"] = (transaction, locked | set(identifiers))
    return result


@dataclass(frozen=True, repr=False)
class LockedMaterialReferences:
    """只能在本事务中消费的精确引用票据，不是跨请求授权令牌。"""

    transaction: object
    tenant_id: str
    actor_id: int
    kind: str
    resource_id: str
    references: tuple[tuple[str, str, int], ...]


async def lock_active_material_reference_set(
    session, context, kind, resource_id, *, additional_asset_ids=()
):
    """B先校原业务动作，随后调用本函数，再锁计划并CAS旧allocation/input_hash。

    清单只从服务端真实引用表读取；取消不能要求旧素材仍READY或旧拥有者仍有权限。
    这里不授予计划权限，也不能在HTTP层直接接受前端资源键后调用。
    """
    _require_transaction(session)
    if not isinstance(context, BusinessContext):
        raise ValueError("释放引用必须使用原业务服务实时授权上下文")
    if kind not in {"ALLOCATION", "EXECUTION"}:
        raise OrbitError(422, "FIELD_INVALID", "历史证据不允许通过计划取消释放", "/kind")
    resource_id = _identifier(resource_id, "/resource_id")
    if not isinstance(additional_asset_ids, (list, tuple)) or len(additional_asset_ids) > 500:
        raise OrbitError(422, "FIELD_INVALID", "待替换素材池最多500项", "/asset_ids")
    additional = {_identifier(item, "/asset_ids") for item in additional_asset_ids}
    await MaterialWorker.lock_clock(session, context.tenant_id)
    params = {"tenant": context.tenant_id, "kind": kind, "resource": resource_id}
    references = (
        (
            await session.execute(
                text("""SELECT id,asset_id FROM orbit_material_reference
                WHERE tenant_id=:tenant AND kind=:kind AND resource_id=:resource AND active=1
                ORDER BY asset_id,id LIMIT 501"""),
                params,
            )
        )
        .mappings()
        .all()
    )
    if len(references) > 500:
        raise OrbitError(409, "REFERENCE_SET_LIMIT", "旧引用集合超过当前有界取消合同")
    identifiers = sorted({item["asset_id"] for item in references} | additional)
    transaction = session.sync_session.get_transaction()
    prior = session.info.get("orbit_material_batch_locks")
    locked = set(prior[1]) if prior and prior[0] is transaction else set()
    new_ids = set(identifiers) - locked
    if new_ids and locked and min(new_ids) < max(locked):
        raise ValueError("替换必须先联合旧新素材清单按全局UUID升序加锁")
    records = {}
    if identifiers:
        statement = text("""SELECT id,revision FROM orbit_material_asset
            WHERE tenant_id=:tenant AND id IN :ids ORDER BY id FOR UPDATE""").bindparams(
            bindparam("ids", expanding=True)
        )
        records = {
            row["id"]: row["revision"]
            for row in (
                (
                    await session.execute(
                        statement, {"tenant": context.tenant_id, "ids": identifiers}
                    )
                )
                .mappings()
                .all()
            )
        }
        if set(records) != set(identifiers):
            raise OrbitError(409, "REFERENCE_INTEGRITY", "旧引用素材元数据缺失，拒绝丢弃证据")
    locked_references = (
        (
            await session.execute(
                text("""SELECT id,asset_id FROM orbit_material_reference
                WHERE tenant_id=:tenant AND kind=:kind AND resource_id=:resource AND active=1
                ORDER BY asset_id,id LIMIT 501 FOR UPDATE"""),
                params,
            )
        )
        .mappings()
        .all()
    )
    snapshot = tuple((r["id"], r["asset_id"]) for r in references)
    if snapshot != tuple((r["id"], r["asset_id"]) for r in locked_references):
        raise OrbitError(409, "REFERENCE_SET_CHANGED", "旧分配引用集合已变化")
    session.info["orbit_material_batch_locks"] = (transaction, locked | set(identifiers))
    ticket = LockedMaterialReferences(
        transaction,
        context.tenant_id,
        context.actor_id,
        kind,
        resource_id,
        tuple((ref, asset, records[asset]) for ref, asset in snapshot),
    )
    session.info.setdefault("orbit_material_release_tickets", []).append(ticket)
    return ticket


async def deactivate_locked_material_references(session, context, ticket, request_id):
    """调用前B必须成功CAS旧分配版本/input_hash；任意后续失败由外层统一回滚。"""
    _require_transaction(session)
    request_id = _identifier(request_id, "/request_id")
    tickets = session.info.get("orbit_material_release_tickets", [])
    if (
        not isinstance(ticket, LockedMaterialReferences)
        or not any(item is ticket for item in tickets)
        or ticket.transaction is not session.sync_session.get_transaction()
        or ticket.tenant_id != context.tenant_id
        or ticket.actor_id != context.actor_id
    ):
        raise ValueError("释放票据必须来自当前调用者的同一事务和精确业务键")
    for reference, asset, revision in ticket.references:
        params = {
            "tenant": ticket.tenant_id,
            "kind": ticket.kind,
            "resource": ticket.resource_id,
            "reference": reference,
            "asset": asset,
            "revision": revision,
            "actor": context.actor_id,
            "request": request_id,
            "event": str(uuid4()),
        }
        changed = await session.execute(
            text("""UPDATE orbit_material_reference SET active=0
            WHERE tenant_id=:tenant AND id=:reference AND asset_id=:asset
            AND kind=:kind AND resource_id=:resource AND active=1"""),
            params,
        )
        if changed.rowcount != 1:
            raise OrbitError(409, "REFERENCE_SET_CHANGED", "旧分配引用已变化，必须整体回滚")
        params["change"] = canonical(
            {
                "reference": {
                    "id": reference,
                    "kind": ticket.kind,
                    "resource_id": ticket.resource_id,
                    "active": {"before": True, "after": False},
                }
            }
        )
        await session.execute(
            text("""INSERT INTO orbit_material_audit
            (id,tenant_id,actor_id,action,resource_id,revision,request_id,change_json)
            VALUES(:event,:tenant,:actor,'MATERIAL_REFERENCE_RELEASED',:asset,:revision,:request,:change)"""),
            params,
        )
        await session.execute(
            text("""INSERT INTO orbit_material_outbox(event_id,tenant_id,resource_id,revision)
            VALUES(:event,:tenant,:asset,:revision)"""),
            params,
        )
    if ticket.references:
        await session.execute(
            text("UPDATE orbit_material_clock SET revision=revision+1 WHERE tenant_id=:tenant"),
            {"tenant": ticket.tenant_id},
        )
    session.info["orbit_material_release_tickets"] = [
        item for item in tickets if item is not ticket
    ]
    return len(ticket.references)


async def register_active_material_references(
    session, context, owner_user_id, owner_team_id, assets, kind, resource_id, request_id
):
    """ALLOCATION/EXECUTION原种类；历史证据有不同晚到/冻结归属合同，不能强行套READY。"""
    _require_transaction(session)
    if kind not in {"ALLOCATION", "EXECUTION"}:
        raise OrbitError(422, "FIELD_INVALID", "此入口仅登记活跃分配或执行引用", "/kind")
    resource_id = _identifier(resource_id, "/resource_id")
    request_id = _identifier(request_id, "/request_id")
    if not isinstance(assets, dict) or not assets:
        raise OrbitError(422, "FIELD_INVALID", "引用必须包含完整冻结素材清单", "/assets")
    identifiers = list(assets)
    try:
        revisions = {key: value["revision"] for key, value in assets.items()}
        hashes = {key: value["sha256"] for key, value in assets.items()}
    except (KeyError, TypeError):
        raise OrbitError(422, "FIELD_INVALID", "冻结素材缺版本或摘要", "/assets") from None
    identifiers = normalize_selection(identifiers, revisions, hashes)
    prior = session.info.get("orbit_material_batch_locks")
    transaction = session.sync_session.get_transaction()
    if not prior or prior[0] is not transaction or not set(identifiers) <= prior[1]:
        raise ValueError("登记引用前必须在本事务内、计划行加锁之前取得全部素材锁")
    current = await require_allocation_assets(
        session, context, owner_user_id, owner_team_id, identifiers, revisions, hashes
    )
    if any(not value["execution_eligible"] for value in current.values()):
        raise OrbitError(409, "ANTIVIRUS_UNVERIFIED", "素材缺少当前对象完整病毒扫描证据")
    result = {}
    changed = False
    for identifier in sorted(current):
        params = {
            "tenant": context.tenant_id,
            "asset": identifier,
            "kind": kind,
            "resource": resource_id,
        }
        existing = await one(
            session,
            """SELECT id,active FROM orbit_material_reference
            WHERE tenant_id=:tenant AND asset_id=:asset AND kind=:kind
            AND resource_id=:resource FOR UPDATE""",
            params,
        )
        if existing is not None and existing["active"]:
            result[identifier] = existing["id"]
            continue
        reference = existing["id"] if existing else str(uuid4())
        if existing:
            await session.execute(
                text(
                    "UPDATE orbit_material_reference SET active=1 "
                    "WHERE tenant_id=:tenant AND asset_id=:asset AND id=:id"
                ),
                params | {"id": reference},
            )
        else:
            await session.execute(
                text("""INSERT INTO orbit_material_reference
                (tenant_id,asset_id,id,kind,resource_id,active)
                VALUES(:tenant,:asset,:id,:kind,:resource,1)"""),
                params | {"id": reference},
            )
        event = str(uuid4())
        audit = params | {
            "event": event,
            "request": request_id,
            "revision": current[identifier]["revision"],
            "actor": context.actor_id,
            "change": canonical(
                {
                    "reference": {
                        "id": reference,
                        "kind": kind,
                        "resource_id": resource_id,
                        "active": {"before": bool(existing and existing["active"]), "after": True},
                    }
                }
            ),
        }
        await session.execute(
            text("""INSERT INTO orbit_material_audit
            (id,tenant_id,actor_id,action,resource_id,revision,request_id,change_json)
            VALUES(:event,:tenant,:actor,'MATERIAL_REFERENCE_ADDED',:asset,:revision,:request,:change)"""),
            audit,
        )
        await session.execute(
            text(
                "INSERT INTO orbit_material_outbox(event_id,tenant_id,resource_id,revision) "
                "VALUES(:event,:tenant,:asset,:revision)"
            ),
            audit,
        )
        changed = True
        result[identifier] = reference
    if changed:
        await session.execute(
            text("UPDATE orbit_material_clock SET revision=revision+1 WHERE tenant_id=:tenant"),
            {"tenant": context.tenant_id},
        )
    return result
