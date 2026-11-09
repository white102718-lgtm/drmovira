"""规则专属完整账户选择读取；原私有snapshot不放宽，不继承计划500限制。"""

import hashlib
import json
from dataclasses import dataclass, field

from sqlalchemy import bindparam, text

from orbit_api.account_access import clock
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.rule_access import assert_access, assert_owner, readable, revalidate_owner
from orbit_api.rule_contract import MAX_SAFE, identifier
from orbit_api.rule_editor_scope_contract import parse_scope_write

MAX_RULE_ACCOUNTS = 50000
MEMBER_BATCH = 1000


@dataclass(frozen=True)
class RuleMember:
    account_id: str
    owner_user_id: str
    owner_team_id: str
    currency: str | None
    revision: int


@dataclass(frozen=True, repr=False)
class FrozenRuleScope:
    snapshot_id: str
    snapshot_hash: str
    member_hash: str
    account_clock_revision: int
    members: tuple[RuleMember, ...]
    _access: object = field(repr=False)
    _owner: object = field(repr=False)
    source_kind: str = "ACCOUNT"
    _target_rule_id: str | None = field(default=None, repr=False)


def changed():
    raise OrbitError(409, "RULE_ACCOUNT_SCOPE_CHANGED", "规则账户范围已变化或不在双方当前交集")


def _member(row, access, owner):
    if (
        row["id"] is None
        or not readable(access.current, access.managed_team_ids, row)
        or not readable(owner.current, owner.managed_team_ids, row)
    ):
        changed()
    if (
        type(row["revision"]) is not int
        or not 1 <= row["revision"] <= MAX_SAFE
        or row["currency"] is not None
        and (
            not isinstance(row["currency"], str)
            or not row["currency"].isascii()
            or len(row["currency"]) != 3
            or not row["currency"].isupper()
            or not row["currency"].isalpha()
        )
    ):
        changed()
    return RuleMember(
        row["id"], row["owner_user_id"], row["owner_team_id"], row["currency"], row["revision"]
    )


async def resolve_scope_source(session, access, snapshot_id):
    """account clock后固定ACCOUNT→RULE当前锁；两源碰撞不猜优先级。

    RULE行独占串行首次消费。不能把返回行当成公开/私有scope读取授权。
    """
    assert_access(session, access)
    params = {
        "tenant": access.current.tenant_id,
        "id": identifier(snapshot_id, "/scope_snapshot_id"),
    }
    account = (
        (
            await session.execute(
                text(
                    "SELECT actor_id,scope_version,auth_fingerprint,member_count,members_hash,"
                    "ready,cleanup_requested FROM orbit_account_scope_snapshot "
                    "WHERE tenant_id=:tenant AND id=:id FOR SHARE"
                ),
                params,
            )
        )
        .mappings()
        .first()
    )
    rule = (
        (
            await session.execute(
                text(
                    "SELECT * FROM orbit_rule_editor_scope_snapshot "
                    "WHERE tenant_id=:tenant AND id=:id FOR UPDATE"
                ),
                params,
            )
        )
        .mappings()
        .first()
    )
    if account is not None and rule is not None:
        raise OrbitError(409, "RULE_SCOPE_SOURCE_AMBIGUOUS", "范围UUID存在两种来源，不能猜测归属")
    if rule is not None:
        return "RULE", dict(rule)
    if account is not None:
        return "ACCOUNT", dict(account)
    raise OrbitError(404, "NOT_FOUND", "范围不存在或不属于当前创建人员")


def validate_rule_scope_header(snapshot):
    """独立列与完整冻结intent一致；不把来源JSON/hash本身当权限。"""
    try:
        raw = snapshot["request_json"]
        intent = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        if not isinstance(intent, dict) or set(intent) != {
            "action",
            "rule_id",
            "rule_revision",
            "ownership",
            "selection",
        }:
            changed()
        revision = intent["rule_revision"]
        body = {key: value for key, value in intent.items() if key != "rule_revision"}
        value = parse_scope_write(canonical(body).encode())
        if (
            hashlib.sha256(canonical(intent).encode()).hexdigest() != snapshot["request_hash"]
            or value.context.action != snapshot["action"]
            or value.context.rule_id != snapshot["rule_id"]
            or value.context.owner_user_id != snapshot["owner_user_id"]
            or value.context.owner_team_id != snapshot["owner_team_id"]
            or revision != snapshot["rule_revision"]
            or value.context.action == "CREATE"
            and revision is not None
            or value.context.action == "UPDATE"
            and (type(revision) is not int or not 1 <= revision <= MAX_SAFE)
        ):
            changed()
    except (OrbitError, KeyError, ValueError, TypeError, UnicodeError):
        changed()


async def rule_scope_bound(session, access, snapshot_id, rule_id):
    """调用方已独占RULE snapshot；索引精确逆查，不扫描其它业务scope。"""
    params = {"tenant": access.current.tenant_id, "id": snapshot_id, "rule": rule_id}
    foreign = (
        (
            await session.execute(
                text(
                    "SELECT rule_id FROM orbit_rule_scope_manifest WHERE tenant_id=:tenant "
                    "AND source_kind='RULE' AND rule_source_snapshot_id=:id AND rule_id<>:rule "
                    "LIMIT 1 FOR SHARE"
                ),
                params,
            )
        )
        .mappings()
        .first()
    )
    if foreign is not None:
        raise OrbitError(409, "RULE_SCOPE_ALREADY_BOUND", "规则账户范围已绑定其它规则")
    same = (
        (
            await session.execute(
                text(
                    "SELECT rule_id FROM orbit_rule_scope_manifest WHERE tenant_id=:tenant "
                    "AND source_kind='RULE' AND rule_source_snapshot_id=:id AND rule_id=:rule "
                    "LIMIT 1 FOR SHARE"
                ),
                params,
            )
        )
        .mappings()
        .first()
    )
    return same is not None


async def verify_reused_scope_source(session, access, snapshot_id, manifest, rule_id):
    """已公开同Rule manifest协作重用不借私有creator权限，但来源必须精确相符。"""
    kind, snapshot = await resolve_scope_source(session, access, snapshot_id)
    if (
        kind != manifest["source_kind"]
        or manifest["rule_id"] != rule_id
        or snapshot.get("ready") != 1
        or snapshot["members_hash"] != manifest["source_snapshot_hash"]
        or snapshot["member_count"] != manifest["member_count"]
    ):
        changed()
    if kind == "RULE":
        validate_rule_scope_header(snapshot)
        if snapshot["action"] == "UPDATE" and snapshot["rule_id"] != rule_id:
            changed()
        if not await rule_scope_bound(session, access, snapshot_id, rule_id):
            changed()
    return kind


async def capture_rule_scope(
    session, access, snapshot_id, owner, *, target_rule_id=None, expected=None
):
    """按来源锁完成后调用：account clock→原snapshot→排序member/account。

    整包上限50000，1000一批，无逐账户SQL；无写入。返回的完整tuple供未来057
    同事务插入Rule专属不可变manifest，外层未提交不能声称已经冻结持久成功。
    """
    assert_owner(session, access, owner)
    await revalidate_owner(session, access, owner)
    snapshot_id = identifier(snapshot_id, "/scope_snapshot_id")
    version = await clock(session, access.current)
    params = {
        "tenant": access.current.tenant_id,
        "actor": access.current.actor_id,
        "id": snapshot_id,
    }
    kind, snapshot = await resolve_scope_source(session, access, snapshot_id)
    if (
        snapshot["actor_id"] != access.current.actor_id
        or snapshot.get("ready") != 1
        or snapshot.get("cleanup_requested", 0) != 0
    ):
        raise OrbitError(404, "NOT_FOUND", "范围不存在或不属于当前创建人员")
    if kind == "RULE":
        target_rule_id = identifier(target_rule_id, "/rule_id")
        validate_rule_scope_header(snapshot)
        if (
            snapshot["owner_user_id"] != owner.current.subject_id
            or snapshot["owner_team_id"] != owner.current.team_id
            or snapshot["owner_auth_fingerprint"] != owner.auth_fingerprint
        ):
            changed()
        bound = await rule_scope_bound(session, access, snapshot_id, target_rule_id)
        if access.permission == "rules.create":
            if snapshot["action"] != "CREATE" or snapshot["rule_id"] is not None or bound:
                changed()
        elif access.permission == "rules.edit":
            if snapshot["action"] == "CREATE":
                if not bound:
                    changed()
            elif (
                snapshot["rule_id"] != target_rule_id
                or not bound
                and (type(expected) is not int or snapshot["rule_revision"] != expected)
            ):
                changed()
        else:
            raise ValueError("RULE_SCOPE_CREATE_EDIT_ONLY")
    if (
        snapshot["actor_id"] != access.current.actor_id
        or snapshot["scope_version"] != access.auth_version
        or snapshot["auth_fingerprint"] != access.auth_fingerprint
    ):
        changed()
    if (
        type(snapshot["member_count"]) is not int
        or not 1 <= snapshot["member_count"] <= MAX_RULE_ACCOUNTS
    ):
        raise OrbitError(422, "RULE_ACCOUNT_LIMIT", "规则必须选择1至50000个账户，不允许截断")
    after, result, original_root = "", [], hashlib.sha256(b"[")
    while True:
        rows = list(
            (
                await session.execute(
                    text(
                        "SELECT m.account_id,m.external_id,m.name,m.account_revision,"
                        "m.owner_user_id AS frozen_owner,m.owner_team_id AS frozen_team,"
                        "m.currency AS frozen_currency,"
                        "a.id,a.owner_user_id,a.owner_team_id,a.currency,a.revision "
                        + (
                            "FROM orbit_account_scope_member m LEFT JOIN orbit_ad_account a "
                            if kind == "ACCOUNT"
                            else "FROM orbit_rule_editor_scope_member m "
                            "LEFT JOIN orbit_ad_account a "
                        )
                        + "ON a.tenant_id=m.tenant_id AND a.id=m.account_id "
                        "WHERE m.tenant_id=:tenant AND m.snapshot_id=:id AND m.account_id>:after "
                        "ORDER BY m.account_id LIMIT 1000 FOR SHARE OF m,a"
                    ),
                    params | {"after": after},
                )
            ).mappings()
        )
        if not rows:
            break
        for row in rows:
            if row["account_id"] <= after or row["id"] != row["account_id"]:
                changed()
            after = row["account_id"]
            if len(result) >= MAX_RULE_ACCOUNTS:
                raise OrbitError(422, "RULE_ACCOUNT_LIMIT", "规则范围超过50000，不允许截断")
            if result:
                original_root.update(b",")
            original_root.update(
                canonical(
                    [
                        row["account_id"],
                        row["external_id"],
                        row["name"],
                        row["account_revision"],
                        row["frozen_owner"],
                        row["frozen_team"],
                        row["frozen_currency"],
                    ]
                ).encode()
            )
            result.append(_member(row, access, owner))
    original_root.update(b"]")
    if (
        len(result) != snapshot["member_count"]
        or original_root.hexdigest() != snapshot["members_hash"]
    ):
        changed()
    # Rule选择身份仅是完整有序ID集合；改名不令选择成员变化或改写原快照历史。
    member_hash = hashlib.sha256(canonical([row.account_id for row in result]).encode()).hexdigest()
    return FrozenRuleScope(
        snapshot_id,
        snapshot["members_hash"],
        member_hash,
        version,
        tuple(result),
        access,
        owner,
        kind,
        target_rule_id,
    )


async def revalidate_rule_members(session, access, owner, members):
    """未来simulate/enable/runtime使用专属manifest，永不冒充原snapshot creator。

    只沿不可变完整ID集合重验当前双方scope。显示名/无关revision更新不改选择身份；
    当前账户元数据返回给事实适配器按每对象币种解释，不沿Plan强制同owner/同币种。
    """
    assert_owner(session, access, owner)
    await revalidate_owner(session, access, owner)
    if not isinstance(members, tuple) or not 1 <= len(members) <= MAX_RULE_ACCOUNTS:
        raise ValueError("规则必须提供完整有界不可变manifest成员")
    if any(not isinstance(row, RuleMember) for row in members):
        raise ValueError("规则manifest成员类型无效")
    ids = [identifier(row.account_id, "/scope_snapshot_id") for row in members]
    if ids != sorted(set(ids)):
        raise ValueError("规则manifest必须唯一且按UUID排序")
    await clock(session, access.current)
    result = []
    statement = text(
        "SELECT id,owner_user_id,owner_team_id,currency,revision FROM orbit_ad_account "
        "WHERE tenant_id=:tenant AND id IN :ids ORDER BY id FOR SHARE"
    ).bindparams(bindparam("ids", expanding=True))
    for offset in range(0, len(ids), MEMBER_BATCH):
        selected = ids[offset : offset + MEMBER_BATCH]
        rows = list(
            (
                await session.execute(
                    statement,
                    {
                        "tenant": access.current.tenant_id,
                        "ids": selected,
                    },
                )
            ).mappings()
        )
        if [row["id"] for row in rows] != selected:
            changed()
        result.extend(_member(row, access, owner) for row in rows)
    return tuple(result)
