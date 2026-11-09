"""标签分类原合同查询字段；日期/事实范围未定义前明确拒绝，不默默忽略。"""

from orbit_api.configuration import short_text
from orbit_api.errors import OrbitError

TAXONOMY_QUERY_FIELDS = {
    "q",
    "cursor",
    "page_size",
    "status",
    "date_from",
    "date_to",
    "operator_user_id",
    "channel_id",
    "metric_profile_id",
    "entity_type",
}


def parse_taxonomy_filters(raw):
    if set(raw) - TAXONOMY_QUERY_FIELDS:
        raise OrbitError(400, "UNKNOWN_FIELD", "此接口不接受该查询参数")
    if "cursor" in raw and not 1 <= len(raw["cursor"]) <= 2048:
        raise OrbitError(422, "FIELD_INVALID", "分类标签游标长度无效", "/cursor")
    for field in (
        "date_from",
        "date_to",
        "operator_user_id",
        "channel_id",
        "metric_profile_id",
        "entity_type",
    ):
        if field in raw:
            raise OrbitError(422, "FILTER_UNSUPPORTED", "该目录筛选组合尚未定义或接入", "/" + field)
    if raw.get("page_size", "50") not in {"20", "50", "100", "200"}:
        raise OrbitError(422, "FIELD_INVALID", "分页数量无效", "/page_size")
    if "status" in raw and raw["status"] not in {"ENABLED", "DISABLED"}:
        raise OrbitError(422, "FIELD_INVALID", "分类标签状态无效", "/status")
    return {
        "q": short_text(raw.get("q", ""), 100, "/q", required=False),
        "status": raw.get("status", ""),
        "page_size": int(raw.get("page_size", "50")),
    }
