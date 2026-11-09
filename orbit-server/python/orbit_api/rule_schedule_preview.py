"""未来五次时间预览技术扩展；纯计算不持久、不建立clock或授予启用资格。"""

from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text

from orbit_api.configuration import _parse_json
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.reference_access import verify_csrf
from orbit_api.rule_access import authorize_rule, require_rule_visible, revalidate_access
from orbit_api.rule_contract import MAX_SAFE, Schedule, identifier, invalid, parse_schedule
from orbit_api.rule_schedule import preview_schedule
from orbit_api.rule_store import RuleStore

MAX_BODY = 16 * 1024  # 内部请求内存预算，不改变原Schedule字段合同。


@dataclass(frozen=True, slots=True)
class SchedulePreviewRequest:
    action: str
    rule_id: str | None
    rule_revision: int | None
    schedule: Schedule


def parse_preview_request(raw: bytes) -> SchedulePreviewRequest:
    if type(raw) is not bytes:
        raise ValueError("SCHEDULE_PREVIEW_RAW_BYTES_REQUIRED")
    if len(raw) > MAX_BODY:
        raise OrbitError(413, "BODY_TOO_LARGE", "时间预览正文超过内部大小限制")
    value = _parse_json(raw)
    if not isinstance(value, dict) or set(value) != {
        "action",
        "rule_id",
        "rule_revision",
        "schedule",
    }:
        raise OrbitError(400, "INVALID_STRUCTURE", "时间预览必须提供四个定义字段")
    action = value["action"]
    if type(action) is not str or action not in {"CREATE", "UPDATE"}:
        invalid("/action")
    rule_id, revision = value["rule_id"], value["rule_revision"]
    if action == "CREATE":
        if rule_id is not None or revision is not None:
            invalid("/rule_id", "新建预览不能携带已有规则或版本")
    else:
        rule_id = identifier(rule_id, "/rule_id")
        if type(revision) is not int or not 1 <= revision <= MAX_SAFE:
            invalid("/rule_revision")
    return SchedulePreviewRequest(action, rule_id, revision, parse_schedule(value["schedule"]))


def unavailable():
    raise OrbitError(503, "RULE_SCHEDULE_PREVIEW_UNAVAILABLE", "当前规则版本或UTC参考时间不完整")


def _reference(value):
    if not isinstance(value, datetime):
        unavailable()
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _utc_text(value):
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def schedule_preview_response(schedule, reference):
    schedule = parse_schedule(schedule.model_dump() if isinstance(schedule, Schedule) else schedule)
    reference = _reference(reference)
    result = preview_schedule(schedule, reference, limit=5)
    zone = ZoneInfo(schedule.timezone)
    return {
        "reference_at": _utc_text(reference),
        "timezone": schedule.timezone,
        "slots": [
            {
                "local_time": slot.astimezone(zone).isoformat(timespec="seconds"),
                "utc_time": _utc_text(slot),
            }
            for slot in result.slots
        ],
        "skipped_local_times": [
            {
                "local_time": wall.isoformat(timespec="seconds"),
                "reason_code": "DST_NONEXISTENT_LOCAL_TIME",
            }
            for wall in result.skipped_local_times
        ],
    }


class RuleSchedulePreviewStore:
    def __init__(self, tokens):
        self.tokens = tokens

    async def preview(self, session, actor, authorization, csrf, request):
        if type(request) is not SchedulePreviewRequest:
            raise ValueError("SCHEDULE_PREVIEW_PARSED_REQUEST_REQUIRED")
        # 不保留调用者可能在授权await期间修改的Schedule模型引用。
        request = parse_preview_request(
            canonical(
                {
                    "action": request.action,
                    "rule_id": request.rule_id,
                    "rule_revision": request.rule_revision,
                    "schedule": request.schedule.model_dump(),
                }
            ).encode()
        )
        access = await authorize_rule(
            session, actor, "rules.create" if request.action == "CREATE" else "rules.edit"
        )
        try:
            verify_csrf(self.tokens, access.current, authorization, csrf)
        except OrbitError:
            raise OrbitError(403, "CSRF_INVALID", "规则时间预览会话校验已失效") from None
        params = {"tenant": access.current.tenant_id}
        clock = (
            (
                await session.execute(
                    text(
                        "SELECT revision,UTC_TIMESTAMP(6) AS reference_at FROM orbit_rule_clock "
                        "WHERE tenant_id=:tenant FOR SHARE"
                    ),
                    params,
                )
            )
            .mappings()
            .first()
        )
        if request.action == "UPDATE":
            head = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM orbit_rule_head WHERE tenant_id=:tenant "
                            "AND id=:id FOR SHARE"
                        ),
                        params | {"id": request.rule_id},
                    )
                )
                .mappings()
                .first()
            )
            require_rule_visible(access, head)
            if clock is None:
                unavailable()
            if type(head["revision"]) is not int or not 1 <= head["revision"] <= MAX_SAFE:
                unavailable()
            if head["revision"] != request.rule_revision:
                raise OrbitError(409, "REVISION_CONFLICT", "规则已变化，请重新读取后预览")
            version = (
                (
                    await session.execute(
                        text(
                            "SELECT * FROM orbit_rule_version WHERE tenant_id=:tenant "
                            "AND rule_id=:id "
                            "AND revision=:revision FOR SHARE"
                        ),
                        params | {"id": request.rule_id, "revision": request.rule_revision},
                    )
                )
                .mappings()
                .first()
            )
            if (
                version is None
                or any(
                    head[key] != version[key]
                    for key in (
                        "tenant_id",
                        "revision",
                        "name",
                        "owner_user_id",
                        "owner_team_id",
                        "state",
                        "target_level",
                        "metric_profile_id",
                        "manifest_id",
                    )
                )
                or version["rule_id"] != head["id"]
            ):
                unavailable()
            try:
                RuleStore.public(dict(head) | dict(version) | {"id": head["id"]})
            except OrbitError:
                unavailable()
        if clock is None:
            # CREATE首次使用无需已有Rule，不创建水位或伪造revision0。
            reference = (await session.execute(text("SELECT UTC_TIMESTAMP(6)"))).scalar_one()
        else:
            if type(clock["revision"]) is not int or not 1 <= clock["revision"] <= MAX_SAFE:
                unavailable()
            reference = clock["reference_at"]
        result = schedule_preview_response(request.schedule, reference)
        await revalidate_access(session, access)
        return result
