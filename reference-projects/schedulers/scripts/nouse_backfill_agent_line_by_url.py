"""
根据 landing_url 回填代理线信息。

对 ad 层级中有 landing_url 但 agent_line 为空的记录，
通过 match_agent_line_by_url 匹配，回填 agent_line / placer_id / department / game_platform。
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from conf.log_conf import init
from db.clients import mongo_client, mongo_client_user, mysql_client
from utils.common import url_variants

UK_COLUMNS = {
    "ad_daily_detail": [
        "date",
        "ad_platform",
        "timezone_name",
        "account_id",
        "campaign_id",
        "ad_set_id",
        "ad_id",
    ],
    "ad_hourly_detail": [
        "date",
        "ad_platform",
        "timezone_name",
        "account_id",
        "campaign_id",
        "ad_set_id",
        "ad_id",
    ],
}
FILL_COLUMNS = ["agent_line", "placer_id", "department", "game_platform"]


def backfill_agent_line_by_url(lookback_hours: int = 3, only_null: bool = True):
    """回填最近 N 小时内有 landing_url 的广告数据的代理线信息

    Args:
        lookback_hours: 回看小时数
        only_null: True 只处理 agent_line 为空的记录，False 处理全部记录
    """

    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    start = now - timedelta(hours=lookback_hours)

    day_start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    days = []
    while day_start < now:
        day_end = min(day_start + timedelta(days=1), now)
        days.append(
            (
                max(start, day_start).strftime("%Y-%m-%d %H:%M:%S"),
                day_end.strftime("%Y-%m-%d %H:%M:%S"),
            )
        )
        day_start += timedelta(days=1)

    # 跨天跨表复用的缓存
    agent_line_to_gp: dict[str, str | None] = {}
    optimizer_to_dept: dict[str, str | None] = {}

    for table in ("ad_daily_detail", "ad_hourly_detail"):
        total = 0
        for day_cutoff, day_end in days:
            count = _backfill_table(
                table, day_cutoff, day_end,
                only_null=only_null,
                agent_line_to_gp=agent_line_to_gp,
                optimizer_to_dept=optimizer_to_dept,
            )
            total += count
        logging.info(f"{table}: 回填完成，共 {total} 行")

    logging.info("回填完成")


def _backfill_table(
    table: str,
    cutoff: str,
    end: str,
    batch_size: int = 10000,
    only_null: bool = True,
    agent_line_to_gp: dict[str, str | None] | None = None,
    optimizer_to_dept: dict[str, str | None] | None = None,
) -> int:
    if agent_line_to_gp is None:
        agent_line_to_gp = {}
    if optimizer_to_dept is None:
        optimizer_to_dept = {}
    uk_cols = UK_COLUMNS[table]
    uk_select = ", ".join(uk_cols)

    sql = f"""
        SELECT {uk_select}, objective, landing_url
        FROM {table}
        WHERE level = 'ad'
          AND landing_url IS NOT NULL
          AND landing_url != ''
          {"AND agent_line IS NULL" if only_null else ""}
          AND objective IN ('OUTCOME_TRAFFIC', 'OUTCOME_SALES', 'OUTCOME_APP_PROMOTION')
          AND china_date >= '{cutoff}'
          AND china_date < '{end}'
    """
    rows = mysql_client.read(sql)

    if not rows:
        return 0

    # 收集所有去重的 landing_url，批量生成变体
    unique_urls = {row[len(uk_cols) + 1] for row in rows}
    all_variants = []
    url_variant_map: dict[str, str] = {}  # variant -> original_url
    for url in unique_urls:
        for v in url_variants(url):
            all_variants.append(v)
            url_variant_map[v] = url

    # 批量查询 MongoDB，一次拿到所有匹配的 agent_line_config
    docs = list(mongo_client["agent_line_config"].find(
        {"history_package_urls": {"$in": all_variants}},
        {"_id": 1, "optimizer": 1, "history_package_urls": 1},
    ))

    if not docs:
        return 0

    # 只查缓存中没有的 agent_line
    agent_lines = [doc["_id"] for doc in docs]
    new_agent_lines = [al for al in agent_lines if al not in agent_line_to_gp]
    if new_agent_lines:
        platform_docs = mongo_client["platform_config"].find(
            {"agent_lines": {"$in": new_agent_lines}},
            {"_id": 1, "agent_lines": 1},
        )
        for pdoc in platform_docs:
            for al in pdoc.get("agent_lines", []):
                if al in new_agent_lines:
                    agent_line_to_gp[al] = pdoc["_id"]
        # 没匹配到的也记录，避免重复查询
        for al in new_agent_lines:
            agent_line_to_gp.setdefault(al, None)

    # 只查缓存中没有的 optimizer
    optimizers = {doc.get("optimizer") for doc in docs if doc.get("optimizer")}
    new_optimizers = [o for o in optimizers if o not in optimizer_to_dept]
    if new_optimizers:
        user_docs = mongo_client_user["user"].find(
            {"$or": [{"real_name": {"$in": new_optimizers}},
                     {"full_name": {"$in": new_optimizers}}]},
            {"real_name": 1, "full_name": 1, "department": 1},
        )
        for u in user_docs:
            dept = u.get("department")
            if u.get("real_name"):
                optimizer_to_dept[u["real_name"]] = dept
            if u.get("full_name"):
                optimizer_to_dept[u["full_name"]] = dept
        for o in new_optimizers:
            optimizer_to_dept.setdefault(o, None)

    # 构建 url -> (agent_line, placer_id, department, game_platform) 映射
    url_match_cache: dict[str, tuple] = {}
    for doc in docs:
        agent_line = doc["_id"]
        optimizer = doc.get("optimizer")
        department = optimizer_to_dept.get(optimizer) if optimizer else None
        game_platform = agent_line_to_gp.get(agent_line)
        matched = (agent_line, optimizer, department, game_platform)
        for pkg_url in doc.get("history_package_urls") or []:
            original_url = url_variant_map.get(pkg_url)
            if original_url:
                url_match_cache[original_url] = matched

    # 按匹配结果组装待写入行
    insert_columns = uk_cols + FILL_COLUMNS
    columns_str = ", ".join(insert_columns)
    placeholders = ", ".join(["%s"] * len(insert_columns))

    matched_rows = []
    for row in rows:
        uk_values = list(row[: len(uk_cols)])
        landing_url = row[len(uk_cols) + 1]

        result = url_match_cache.get(landing_url)
        if result:
            matched_rows.append(tuple(uk_values + list(result)))

    if not matched_rows:
        return 0

    total = len(matched_rows)
    insert_sql = f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})"
    with mysql_client.session() as cur:
        cur.execute("SET enable_unique_key_partial_update = true")
        cur.execute("SET enable_insert_strict = false")
        for i in range(0, total, batch_size):
            cur.executemany(insert_sql, matched_rows[i : i + batch_size])
    logging.info(f"{table}: [{cutoff[:10]}] 回填 {total} 行")
    return total


if __name__ == "__main__":
    init("backfill_agent_line_by_url.py")
    backfill_agent_line_by_url(24 * 3, only_null=False)
    # sed -i -E 's/backfill_agent_line_by_url\([^,]+/backfill_agent_line_by_url(24 * 30/' scripts/backfill_agent_line_by_url.py
