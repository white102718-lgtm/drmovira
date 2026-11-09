"""原合同系列命名预留：真实来源、上海日期及事务占号，不签发执行许可。"""

import unicodedata
from dataclasses import dataclass, replace
from datetime import UTC, date
from uuid import uuid4

from sqlalchemy import text

from orbit_api import launch_access as access
from orbit_api.channel_store import ChannelStore
from orbit_api.configuration_store import _decode
from orbit_api.errors import OrbitError
from orbit_api.launch_contract import uuid_field
from orbit_api.launch_expansion import campaign_name, campaign_slots, naming_date
from orbit_api.launch_plan_source import capture_plan_source
from orbit_api.launch_references import validate_sources
from orbit_api.launch_store import LaunchStore
from orbit_api.reference_access import scope_version, verify_csrf

MAX_SEQUENCE = 10**30 - 1


def normalized_name(value):
    """昵称/姓名沿真实来源NFC规范化；绝不以登录名冒充姓名。"""
    return unicodedata.normalize("NFC", value or "").strip()


def sequence_interval(last, count):
    """只对已锁定序列计算完整区间；溢出或空展开不能保存半批名称。"""
    last = int(last)
    if count < 1 or count > 10000:
        raise OrbitError(422, "NAMING_EMPTY_OR_TOO_LARGE", "展开系列须为1至10000项", "/campaigns")
    if last < 0 or last + count > MAX_SEQUENCE:
        raise OrbitError(409, "NAME_SEQUENCE_EXHAUSTED", "当日命名序列已超出合同上限")
    return range(last + 1, last + count + 1)


def naming_projection(plan):
    """只检查命名相关来源；身份/素材/环境在独立预检阶段校验，不能假装已核验。"""
    return plan | {
        "asset_ids": [],
        "identity_bindings": [],
        "profile_binding_ids": [],
        "campaigns": [
            campaign
            | {"adsets": [group | {"metric_profile_id": None} for group in campaign["adsets"]]}
            for campaign in plan["campaigns"]
        ],
    }


async def database_day(session):
    now = (await session.execute(text("SELECT UTC_TIMESTAMP(3)"))).scalar_one()
    # MySQL UTC_TIMESTAMP不是会话本地时区；驱动返回无tz时显式标UTC。
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return naming_date(now)


@dataclass(frozen=True)
class NamingInput:
    plan_id: str
    revision: int
    payload_hash: str
    day: date
    source_hash: str
    source: dict
    slots: tuple


async def prepare_naming(session, current, plan):
    """无锁计划预读后取人员→账户→渠道来源锁，最后调用方才可锁launch。"""
    directory_revision = await scope_version(session, current)
    value = _decode(plan["payload_json"])
    if plan["state"] not in {"DRAFT", "VALIDATED"}:
        raise OrbitError(409, "PLAN_STATE_CONFLICT", "已提交或归档计划不能重新预留名称")
    if not value.get("channel_id"):
        raise OrbitError(422, "CHANNEL_REQUIRED", "命名须选择真实启用渠道", "/channel_id")
    if not value["account_ids"]:
        raise OrbitError(422, "ACCOUNT_REQUIRED", "命名须选择至少一个账户", "/account_ids")
    slots = tuple(campaign_slots(value))
    sequence_interval(0, len(slots))
    ownership = value["ownership"]
    await access.owner(session, current, ownership)
    person = (
        (
            await session.execute(
                text("""SELECT u.nick_name,b.display_name FROM orbit_business_user b
            JOIN sys_user u ON u.user_id=b.user_id WHERE b.tenant_id=:tenant
            AND b.id=:owner FOR SHARE"""),
                {"tenant": current.tenant_id, "owner": ownership["owner_user_id"]},
            )
        )
        .mappings()
        .one()
    )
    nickname, full_name = (
        normalized_name(person["nick_name"]),
        normalized_name(person["display_name"]),
    )
    if not nickname and not full_name:
        raise OrbitError(
            409, "NAMING_SOURCE_UNAVAILABLE", "负责人昵称和姓名均未知，不能使用登录名代替"
        )
    dependencies = await validate_sources(
        session, current, naming_projection(value), permission="launch.edit"
    )
    channel = await ChannelStore(None).row(session, current, value["channel_id"])
    channel_value = _decode(channel["value_json"])
    source = {
        "plan_payload_hash": plan["payload_hash"],
        "ownership": ownership,
        "channel": channel_value,
        "channel_revision": channel["revision"],
        "nickname": nickname,
        "full_name": full_name,
        "dependencies": dependencies,
        "scope_version": directory_revision,
        "slots": slots,
        "timezone": "Asia/Shanghai",
    }
    return NamingInput(
        plan["id"],
        plan["revision"],
        plan["payload_hash"],
        await database_day(session),
        access.digest(source),
        source,
        slots,
    )


def assert_plan_input(row, prepared, expected):
    if (
        row["revision"] != expected
        or row["revision"] != prepared.revision
        or row["payload_hash"] != prepared.payload_hash
    ):
        raise OrbitError(409, "REVISION_CONFLICT", "计划已变化，请重新读取后预览")
    if row["state"] not in {"DRAFT", "VALIDATED"}:
        raise OrbitError(409, "PLAN_STATE_CONFLICT", "计划状态已变化")


async def bind_naming_source(session, current, locked, prepared):
    """来源锁→launch头锁后再查不可变配置；状态CAS变化不重占命名序号。

    prepared.revision此前是预读的CAS头，仅供assert_plan_input比较；从此处起
    revision专指真实PlanVersion键。外部If-Match和幂等意图仍使用原expected头。
    """
    source = await capture_plan_source(session, current, locked)
    if source.plan_id != prepared.plan_id or source.payload_hash != prepared.payload_hash:
        raise OrbitError(409, "REVISION_CONFLICT", "命名配置源已变化，请重新读取")
    return replace(prepared, revision=source.source_revision)


def assert_reservation_input(row, prepared):
    if (
        row["plan_id"] != prepared.plan_id
        or row["plan_revision"] != prepared.revision
        or row["naming_date"] != prepared.day
        or row["source_hash"] != prepared.source_hash
    ):
        raise OrbitError(409, "NAMING_PREVIEW_STALE", "命名日期、来源或计划已变化，请重新预览")


class LaunchNamingStore:
    def __init__(self, tokens):
        self.tokens = tokens

    async def result(self, session, tenant, row, expected_slots):
        items = (
            (
                await session.execute(
                    text("""SELECT slot_key,name,sequence
            FROM orbit_launch_name_item WHERE tenant_id=:tenant AND reservation_id=:id
            ORDER BY ordinal LIMIT 10001"""),
                    {"tenant": tenant, "id": row["id"]},
                )
            )
            .mappings()
            .all()
        )
        if not 1 <= len(items) <= 10000 or [item["slot_key"] for item in items] != [
            "/".join(map(str, slot)) for slot in expected_slots
        ]:
            raise OrbitError(503, "NAMING_RESERVATION_INCOMPLETE", "命名预留记录不完整，不能继续")
        return {
            "id": row["id"],
            "plan_revision": row["plan_revision"],
            "naming_date": row["naming_date"].isoformat(),
            "items": [
                {
                    "slot_key": item["slot_key"],
                    "name": item["name"],
                    "sequence": str(int(item["sequence"])),
                }
                for item in items
            ],
        }

    async def reservation(self, session, current, identifier):
        row = (
            (
                await session.execute(
                    text("""SELECT id,plan_id,plan_revision,naming_date,source_hash
            FROM orbit_launch_name_reservation WHERE tenant_id=:tenant AND id=:id FOR SHARE"""),
                    {"tenant": current.tenant_id, "id": identifier},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise OrbitError(404, "NOT_FOUND", "命名预留不存在或不可见")
        return row

    async def reserve(
        self, session, actor, authorization, csrf, key, identifier, expected, request_id
    ):
        identifier = uuid_field(identifier, ("id",))
        current = await access.context(session, actor, "launch.edit")
        verify_csrf(self.tokens, current, authorization, csrf)
        plans = LaunchStore(self.tokens)
        previous = await plans.row(session, current, identifier, unlocked=True)
        prepared = await prepare_naming(session, current, previous)
        await access.clock(session, current, write=True)
        locked = await plans.row(session, current, identifier, write=True)
        assert_plan_input(locked, prepared, previous["revision"])
        prepared = await bind_naming_source(session, current, locked, prepared)
        # 授权来源共享锁一直持有，锁后再核当前动作而非仅信任前端旧capabilities。
        await access.context(session, actor, "launch.edit")
        if await database_day(session) != prepared.day:
            raise OrbitError(409, "NAMING_DATE_CHANGED", "锁定期间跨上海午夜，请重新预览")
        payload_hash = access.digest([identifier, expected])
        replay = await access.replay(session, current, "plan.naming", key, payload_hash)
        if replay:
            row = await self.reservation(session, current, replay["id"])
            assert_reservation_input(row, prepared)
            result = await self.result(session, current.tenant_id, row, prepared.slots)
            if await database_day(session) != prepared.day:
                raise OrbitError(409, "NAMING_DATE_CHANGED", "读取期间跨上海午夜，请重新预览")
            return result
        # 当前来源/权限仍须重验；已成功原键可在旧CAS头重放，新键不能绕过If-Match。
        if locked["revision"] != expected:
            raise OrbitError(409, "REVISION_CONFLICT", "计划已变化，请重新读取后预览")
        values = {
            "tenant": current.tenant_id,
            "plan": identifier,
            "revision": prepared.revision,
            "day": prepared.day,
            "hash": prepared.source_hash,
        }
        row = (
            (
                await session.execute(
                    text("""SELECT id,plan_id,plan_revision,naming_date,source_hash
            FROM orbit_launch_name_reservation WHERE tenant_id=:tenant AND plan_id=:plan
            AND plan_revision=:revision AND naming_date=:day AND source_hash=:hash FOR SHARE"""),
                    values,
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            row = await self.create_reservation(session, current, prepared, request_id)
        result = await self.result(session, current.tenant_id, row, prepared.slots)
        if await database_day(session) != prepared.day:
            raise OrbitError(409, "NAMING_DATE_CHANGED", "预留期间跨上海午夜，请重新预览")
        await access.remember(session, current, "plan.naming", key, payload_hash, result)
        return result

    async def create_reservation(self, session, current, prepared, request_id):
        channel, ownership = prepared.source["channel"], prepared.source["ownership"]
        values = {
            "tenant": current.tenant_id,
            "channel": channel["id"]
            if "id" in channel
            else prepared.source["dependencies"]["channel"]["id"],
            "owner": ownership["owner_user_id"],
            "day": prepared.day,
        }
        await session.execute(
            text("""INSERT INTO orbit_launch_name_sequence
            (tenant_id,channel_id,owner_user_id,naming_date,last_sequence)
            VALUES(:tenant,:channel,:owner,:day,0)
            ON DUPLICATE KEY UPDATE last_sequence=last_sequence"""),
            values,
        )
        last = (
            await session.execute(
                text("""SELECT last_sequence FROM orbit_launch_name_sequence
            WHERE tenant_id=:tenant AND channel_id=:channel AND owner_user_id=:owner
            AND naming_date=:day FOR UPDATE"""),
                values,
            )
        ).scalar_one()
        sequences = sequence_interval(last, len(prepared.slots))
        identifier = str(uuid4())
        items = []
        for ordinal, (slot, sequence) in enumerate(zip(prepared.slots, sequences, strict=True)):
            items.append(
                {
                    "tenant": current.tenant_id,
                    "reservation": identifier,
                    "ordinal": ordinal,
                    "slot": "/".join(map(str, slot)),
                    "sequence": str(sequence),
                    "name": campaign_name(
                        channel_name=channel.get("name", ""),
                        channel_code=channel["code"],
                        nickname=prepared.source["nickname"],
                        full_name=prepared.source["full_name"],
                        day=prepared.day,
                        sequence=sequence,
                    ),
                }
            )
        await session.execute(
            text("""UPDATE orbit_launch_name_sequence SET last_sequence=:last
            WHERE tenant_id=:tenant AND channel_id=:channel AND owner_user_id=:owner
            AND naming_date=:day"""),
            values | {"last": str(sequences.stop - 1)},
        )
        row = {
            "id": identifier,
            "plan_id": prepared.plan_id,
            "plan_revision": prepared.revision,
            "naming_date": prepared.day,
            "source_hash": prepared.source_hash,
        }
        await session.execute(
            text("""INSERT INTO orbit_launch_name_reservation
            (tenant_id,id,plan_id,plan_revision,naming_date,source_hash,created_at)
            VALUES(:tenant,:id,:plan_id,:plan_revision,:naming_date,:source_hash,UTC_TIMESTAMP(3))"""),
            {"tenant": current.tenant_id} | row,
        )
        for offset in range(0, len(items), 200):
            await session.execute(
                text("""INSERT INTO orbit_launch_name_item
                (tenant_id,reservation_id,ordinal,slot_key,name,sequence)
                VALUES(:tenant,:reservation,:ordinal,:slot,:name,:sequence)"""),
                items[offset : offset + 200],
            )
        await access.event(
            session,
            current,
            "NAME_RESERVATION",
            identifier,
            1,
            "plan.naming",
            request_id,
            {
                "plan_id": prepared.plan_id,
                "plan_revision": prepared.revision,
                "naming_date": prepared.day.isoformat(),
                "source_hash": prepared.source_hash,
                "naming_source": prepared.source,
                "count": len(items),
            },
        )
        return row

    async def verify_current(self, session, actor, identifier, reservation_id, expected):
        """供未来预检/提交显式调用；独立实时核验，返回名不等同完整预检成功。"""
        identifier = uuid_field(identifier, ("id",))
        reservation_id = uuid_field(reservation_id, ("name_reservation_id",))
        current = await access.context(session, actor, "launch.edit")
        plans = LaunchStore(self.tokens)
        previous = await plans.row(session, current, identifier, unlocked=True)
        prepared = await prepare_naming(session, current, previous)
        await access.clock(session, current)
        locked = await plans.row(session, current, identifier)
        assert_plan_input(locked, prepared, expected)
        prepared = await bind_naming_source(session, current, locked, prepared)
        if await database_day(session) != prepared.day:
            raise OrbitError(409, "NAMING_DATE_CHANGED", "命名业务日已变化")
        row = await self.reservation(session, current, reservation_id)
        assert_reservation_input(row, prepared)
        result = await self.result(session, current.tenant_id, row, prepared.slots)
        if await database_day(session) != prepared.day:
            raise OrbitError(409, "NAMING_DATE_CHANGED", "核验期间跨上海午夜，请重新预览")
        return result
