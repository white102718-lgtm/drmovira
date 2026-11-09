"""手动补成效:指定 dev + 指定户 + 日期区间,按小时把历史成效补进 doris。

线上 ad_hourly_detail 的每个小时槽是"当天 0 点到该时刻的累计快照"。过去的日子
FB 不提供当时的快照,本脚本用 hourly breakdown
(`hourly_stats_aggregated_by_advertiser_time_zone`,账户时区逐小时增量)累加还原:
H 点的行 = 0..H-1 小时桶之和,与线上"H 点拉到的当天累计"同语义。

每个 (户, 日) 的步骤(拉取/转换复用线上 review 结构):
  1. pipeline.fetch_all 整日拉取(day 级成效 + 实体,include_frequency/breakdowns 可配)
  2. 追加两份 hourly breakdown 报告(level=ad / level=account)
  3. 01..23 每小时:小时桶累加成"截至该小时"的 bundle → BundleTransform 产行
     (行时间钉在账户本地 H:00)→ 写 hourly + half_hour 两张表
  4. 整日 bundle → transform(review 语义,行时间=次日 00:00)→ 写 hourly/daily/half
     三张表(次日 " 00" 槽 + 当日 daily 定稿),永远放在小时行之后写

注意:
  - FB hourly breakdown 不支持 reach / frequency / unique 类指标,小时行这些列为
    NULL(日级行不受影响);半点槽(HH:30)不补,只补整点。
  - 小时行不往 daily 表级联(线上级联是为了盘中刷新;补历史日中间值无意义,
    daily 只由第 4 步的整日定稿写一次)。
  - 默认只补缺槽:逐 (户, 日) 先查目标库 ad_hourly_detail 已有的小时槽和次日
    " 00" 定稿,已存在的跳过 —— 三张表是 UNIQUE KEY 覆盖写,重写不报错,但会把
    线上真实快照换成重建口径,且小时行拉不到的 reach/unique 类列会被抹成 NULL。
    overwrite_existing=True 才整天强制重写。
  - 不碰 redis 锁、不写 ad_sync_history、不推 ad_sync_done —— 纯手动补数,
    别跟同日期的 review 回填同时跑。
  - 只支持补历史日(date_end 必须早于今天中国日期),今天的数据走线上 hourly。
  - 写生产还是测试库跟线上取法一致:由启动时的 DEPLOY_ENV 决定
    (env_vault/env_conf.py 按 DEPLOY_ENV 加载 .{env}.env → DorisConf),
    mongo(dev 凭据、agent_line 匹配)/redis 同步跟随同一环境。

用法:
  cd schedulers
  改 __main__ 里的配置后:
  DEPLOY_ENV=prod python -m tasks.ad_sync_new.scripts.manual_backfill_insights   # 写生产
  DEPLOY_ENV=test python -m tasks.ad_sync_new.scripts.manual_backfill_insights   # 写测试
  (PowerShell: $env:DEPLOY_ENV="prod"; python -m ...)
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId

from conf import DorisConf, env
from conf.log_conf import init
from db.clients import mysql_client
from db.doris_stream_load import stream_load
from utils.fb_utils import resolve_tz

from tasks.ad_sync_new import pipeline, transform
from tasks.ad_sync_new.airbyte import DateInterval, InsightAsyncJobManager
from tasks.ad_sync_new.consts import (
    ProducerMethod,
    compute_fetch_day,
    effective_account_dt,
)
from tasks.ad_sync_new.dispatcher import (
    _list_account_ids,
    _probe_ads_api_access_tier,
    prepare_base_message,
)
from tasks.ad_sync_new.doris_writer import (
    BACKFILL_MANAGED_COLUMNS,
    HALF_HOUR_TABLE,
    _convert_date_for_daily,
    _convert_date_for_half_hour,
    _convert_date_for_hourly,
)


logger = logging.getLogger(__name__)

HOURLY_BREAKDOWN = "hourly_stats_aggregated_by_advertiser_time_zone"

# hourly breakdown 可同查的求和字段:INSIGHTS_FIELDS 去掉 reach/frequency/unique 类
# (FB 不支持与小时 breakdown 同查)和 cpm/ctr/cpc 等比率(累加时重算)。
HOURLY_SUM_FIELDS = [
    "spend",
    "impressions",
    "clicks",
    "actions",
    "action_values",
    "conversions",
    "inline_link_clicks",
]
# 小时行强制置 NULL:这些指标小时粒度拉不到,_build_aggregated_insight 会把缺失
# 字段求和成 "0",直接写 0 会误导。
HOURLY_NULL_FIELDS = [
    "reach",
    "frequency",
    "unique_clicks",
    "unique_inline_link_clicks",
    "unique_inline_link_click_ctr",
]
HOUR_ID_NAME_FIELDS = (
    "campaign_id", "campaign_name",
    "adset_id", "adset_name",
    "ad_id", "ad_name",
)
STREAM_LOAD_BATCH = 10000


# ── doris 写入(目标库 = 进程 DEPLOY_ENV 对应的 DorisConf,与线上一致) ────────

def _write_table(table: str, rows: List[Dict]) -> None:
    """对齐 doris_writer._write_table 的列过滤(BACKFILL_MANAGED 为 None 不写),分批导入。"""
    payload = [
        {k: v for k, v in row.items() if not (k in BACKFILL_MANAGED_COLUMNS and v is None)}
        for row in rows
    ]
    for i in range(0, len(payload), STREAM_LOAD_BATCH):
        stream_load(table, payload[i:i + STREAM_LOAD_BATCH], flexible=True)


def _write_hour_rows(rows: List[Dict]) -> None:
    if not rows:
        return
    _write_table("ad_hourly_detail", _convert_date_for_hourly(rows))
    _write_table(HALF_HOUR_TABLE, _convert_date_for_half_hour(rows))


def _write_day_rows(rows: List[Dict]) -> None:
    if not rows:
        return
    hourly = _convert_date_for_hourly(rows)
    _write_table("ad_hourly_detail", hourly)
    _write_table("ad_daily_detail", _convert_date_for_daily(hourly))
    _write_table(HALF_HOUR_TABLE, _convert_date_for_half_hour(rows))


# ── hourly breakdown 拉取 ────────────────────────────────────────────────────

def _run_insight_jobs(api, account_id: str, jobs: List) -> Dict[str, Optional[List[Dict]]]:
    """跑一批 InsightAsyncJob,按 _report_name 归集(对齐 fetch_all 的收集循环)。
    某报告放弃时该 key 置 None,和"跑成功但 0 行"区分。"""
    result: Dict[str, Any] = {getattr(j, "_report_name"): [] for j in jobs}
    failed: set = set()
    manager = InsightAsyncJobManager(api=api, jobs=iter(jobs), account_id=account_id)
    for completed in manager.completed_jobs():
        name = getattr(completed, "_report_name", None)
        if not name:
            logger.warning("[manual_backfill] completed job 缺 _report_name: %s", completed)
            continue
        if completed.failed:
            logger.warning("[manual_backfill] 报告 %s 放弃", name)
            failed.add(name)
            continue
        for obj in completed.get_result():
            data = obj.export_all_data() if hasattr(obj, "export_all_data") else dict(obj)
            result[name].append(dict(data))
    for name in failed:
        result[name] = None
    return result


def _fetch_hourly_reports(
    api, account, tz_name: str, fetch_day: str, include_video: bool,
) -> Dict[str, Optional[List[Dict]]]:
    day = datetime.strptime(fetch_day, "%Y-%m-%d").date()
    interval = DateInterval(start=day, end=day)
    ad_fields = (
        list(HOURLY_SUM_FIELDS)
        + (list(pipeline.VIDEO_INSIGHTS_FIELDS) if include_video else [])
        + list(pipeline.AD_LEVEL_EXTRA_FIELDS)
    )
    jobs = [
        pipeline._build_insight_job(
            api=api, account=account, tz_name=tz_name, interval=interval,
            fields=ad_fields, level="ad",
            breakdowns=[HOURLY_BREAKDOWN], name="hourly_ad",
        ),
        pipeline._build_insight_job(
            api=api, account=account, tz_name=tz_name, interval=interval,
            fields=list(HOURLY_SUM_FIELDS) + ["date_start", "date_stop"], level="account",
            breakdowns=[HOURLY_BREAKDOWN],
            primary_key=["date_start", HOURLY_BREAKDOWN], name="hourly_account",
        ),
    ]
    return _run_insight_jobs(api, pipeline._strip_act(account["id"]), jobs)


# ── 小时桶 → 累计行 ──────────────────────────────────────────────────────────

def _hour_of(row: Dict) -> Optional[int]:
    v = row.get(HOURLY_BREAKDOWN) or ""
    try:
        return int(v[:2])
    except ValueError:
        return None


def _merge_action_list(rows: List[Dict], field: str) -> List[Dict]:
    merged: Dict[str, float] = {}
    for row in rows:
        for item in row.get(field) or []:
            at = item.get("action_type")
            merged[at] = merged.get(at, 0.0) + float(item.get("value", 0) or 0)
    return [{"action_type": at, "value": str(int(round(v)))} for at, v in merged.items()]


def _cumulative_insight(buckets: List[Dict], video_fields: List[str]) -> Dict:
    """< H 的小时桶 → "截至 H:00" 的累计行,形状与 day 级 insight 行一致。"""
    agg = transform.BundleTransform._build_aggregated_insight(buckets)
    if not agg:
        return {}
    for f in HOURLY_NULL_FIELDS:
        agg[f] = None
    for vf in video_fields:
        agg[vf] = _merge_action_list(buckets, vf)
    first = buckets[0]
    for k in HOUR_ID_NAME_FIELDS:
        if first.get(k) is not None:
            agg[k] = first[k]
    return agg


class _FixedDtTransform(transform.BundleTransform):
    """行时间钉在指定的账户本地小时(review 日期下父类只会给次日 00:00)。"""

    def __init__(self, message, bundle, fixed_dt: datetime):
        super().__init__(message, bundle)
        self._fixed_dt = fixed_dt

    @property
    def account_date(self) -> datetime:
        return self._fixed_dt


def _build_hour_rows(
    account_message: Dict[str, Any],
    day_bundle: Dict[str, Any],
    hourly_ad: List[Dict],
    hourly_account: Optional[List[Dict]],
    tz_name: str,
    fetch_day: str,
    hours: range,
    video_fields: List[str],
    shared_caches: tuple,
) -> List[Dict]:
    tz = resolve_tz(tz_name)
    day_start = datetime.strptime(fetch_day, "%Y-%m-%d")

    ad_buckets: Dict[str, Dict[int, Dict]] = {}
    for row in hourly_ad:
        h, aid = _hour_of(row), row.get("ad_id")
        if h is not None and aid:
            ad_buckets.setdefault(aid, {})[h] = row
    acct_buckets: Dict[int, Dict] = {}
    for row in hourly_account or []:
        h = _hour_of(row)
        if h is not None:
            acct_buckets[h] = row

    hour_rows: List[Dict] = []
    for hh in hours:
        ad_insights = []
        for buckets in ad_buckets.values():
            cum = _cumulative_insight(
                [buckets[h] for h in sorted(buckets) if h < hh], video_fields,
            )
            if cum:
                ad_insights.append(cum)
        acct_cum = _cumulative_insight(
            [acct_buckets[h] for h in sorted(acct_buckets) if h < hh], [],
        )
        bundle_h = {
            "ad_account": day_bundle.get("ad_account"),
            "campaigns": day_bundle.get("campaigns", []),
            "ad_sets": day_bundle.get("ad_sets", []),
            "ads": day_bundle.get("ads", []),
            "account_insights": [acct_cum] if acct_cum else [],
            "ad_insights": ad_insights,
            "breakdown_age_gender": [],
        }
        t = _FixedDtTransform(
            account_message, bundle_h, day_start.replace(hour=hh, tzinfo=tz),
        )
        t._url_match_cache, t._placer_dept_cache = shared_caches
        rows = t.to_rows()
        # account 级 hourly 报告放弃时不产 account 小时行,避免写出全 NULL 指标行
        if hourly_account is None:
            rows = [r for r in rows if r.get("level") != "account"]
        hour_rows.extend(rows)
    return hour_rows


# ── 缺口检测 ─────────────────────────────────────────────────────────────────

def _existing_slots(account_id: str, fetch_day: str) -> tuple:
    """查目标库该户 fetch_day 已有数据的小时槽(1..23 集合)+ 次日 " 00" 定稿是否存在。
    只查 ad_hourly_detail:三张表由同一次写入产生,hourly 有则其余有。"""
    aid = account_id[4:] if account_id.startswith("act_") else account_id
    next_day = (date.fromisoformat(fetch_day) + timedelta(days=1)).isoformat()
    rows = mysql_client.read(
        "SELECT DISTINCT date FROM ad_hourly_detail "
        f"WHERE account_id = '{aid}' "
        f"AND date >= '{fetch_day} 01:00:00' AND date <= '{next_day} 00:00:00'"
    )
    hours: set = set()
    has_final = False
    for (dt,) in rows:
        if dt.date().isoformat() == fetch_day:
            hours.add(dt.hour)
        elif dt.hour == 0:
            has_final = True
    return hours, has_final


def _fmt_hours(hours: List[int]) -> str:
    if not hours:
        return "-"
    spans, start, prev = [], hours[0], hours[0]
    for h in hours[1:]:
        if h == prev + 1:
            prev = h
            continue
        spans.append((start, prev))
        start = prev = h
    spans.append((start, prev))
    return ",".join(f"{a:02d}" if a == b else f"{a:02d}-{b:02d}" for a, b in spans)


# ── 单 (户, 日) 主流程 ───────────────────────────────────────────────────────

def _backfill_one(
    account_id: str,
    day: str,
    base_message: Dict[str, Any],
    api,
    include_frequency: bool,
    include_breakdowns: bool,
    hourly_include_video: bool,
    overwrite_existing: bool,
    shared_caches: tuple,
) -> Dict[str, Any]:
    account_message = {**base_message, "account_id": account_id, "date": day}
    acct = api.get_account(account_id=account_id)
    tz_name = acct.get("timezone_name")
    if not tz_name:
        return {"ok": False, "error": "no timezone_name"}
    if acct.get("account_status") == 101:
        logger.warning(
            "[manual_backfill] account=%s 已 CLOSED(101),仍尝试拉历史数据", account_id,
        )

    fetch_day = compute_fetch_day(day, tz_name)
    effective = effective_account_dt(day, tz_name)
    # 目标日在账户本地还没走完时,只补到当前已发生的小时,其余槽留给线上 hourly
    candidate = range(1, 24) if effective.hour == 0 else range(1, effective.hour + 1)

    existing_hours: set = set()
    has_final = False
    if not overwrite_existing:
        existing_hours, has_final = _existing_slots(account_id, fetch_day)
    hours = [h for h in candidate if h not in existing_hours]
    write_final = overwrite_existing or not has_final
    if not hours and not write_final:
        logger.warning(
            "[manual_backfill] account=%s day=%s 无缺槽,跳过", account_id, fetch_day,
        )
        return {
            "ok": True, "hour_rows": 0, "day_rows": 0, "hours": "-",
            "note": "无缺槽", "error": None,
        }
    logger.warning(
        "[manual_backfill] account=%s fetch_day=%s 已有槽=%d 待补槽=%s 定稿=%s",
        account_id, fetch_day, len(existing_hours), _fmt_hours(hours),
        "待写" if write_final else "已存在",
    )

    # 1) 整日拉取(review 结构:实体只按 insight 命中兜底)
    bundle = pipeline.fetch_all(
        message=account_message,
        fetch_day=fetch_day,
        include_frequency=include_frequency,
        include_breakdowns=include_breakdowns,
    )
    day_rows = transform.bundle_to_doris_rows(account_message, bundle)

    # 2) hourly breakdown 报告 → 3) 累计小时行(有缺槽才拉)
    hour_rows: List[Dict] = []
    hourly_failed = False
    if hours:
        reports = _fetch_hourly_reports(
            api, acct, tz_name, fetch_day, hourly_include_video,
        )
        hourly_failed = reports["hourly_ad"] is None
        if hourly_failed:
            logger.error(
                "[manual_backfill] account=%s day=%s hourly_ad 报告失败,小时槽未补",
                account_id, day,
            )
        else:
            hour_rows = _build_hour_rows(
                account_message, bundle, reports["hourly_ad"], reports["hourly_account"],
                tz_name, fetch_day, hours,
                list(pipeline.VIDEO_INSIGHTS_FIELDS) if hourly_include_video else [],
                shared_caches,
            )

    # 4) 先写小时行,整日定稿永远最后写;定稿已存在(且未强制重写)则不动 daily
    _write_hour_rows(hour_rows)
    if write_final:
        _write_day_rows(day_rows)

    return {
        "ok": True,
        "hour_rows": len(hour_rows),
        "day_rows": len(day_rows) if write_final else 0,
        "hours": _fmt_hours(hours) if hour_rows else "-",
        "note": None if write_final else "定稿已存在,跳过日级",
        "error": "hourly_ad 报告失败,小时槽未补" if hourly_failed else None,
    }


# ── 入口 ─────────────────────────────────────────────────────────────────────

def main(
    dev_mongo_id: str,
    is_personal: bool,
    account_ids: List[str],
    date_start: str,
    date_end: str,
    include_frequency: bool = True,
    include_breakdowns: bool = True,
    hourly_include_video: bool = True,
    overwrite_existing: bool = False,
) -> None:
    d0, d1 = date.fromisoformat(date_start), date.fromisoformat(date_end)
    today_cn = datetime.now(timezone(timedelta(hours=8))).date()
    if d0 > d1:
        raise SystemExit(f"date_start={date_start} 晚于 date_end={date_end}")
    if d1 >= today_cn:
        raise SystemExit(f"只支持补历史日:date_end={date_end} 须早于今天(中国){today_cn}")
    days = [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]

    logger.warning(
        "[manual_backfill] DEPLOY_ENV=%s → doris=%s(mongo/redis 同环境)",
        env, DorisConf.HOST,
    )

    msg = {
        "_id": dev_mongo_id,
        "date": days[0],
        "type": (
            ProducerMethod.PERSONAL_PRODUCER.value
            if is_personal
            else ProducerMethod.PRODUCER.value
        ),
    }
    prepared = prepare_base_message(msg, history_id=str(ObjectId()))
    if prepared is None:
        raise SystemExit(f"prepare_base_message 失败(dev 不存在/禁用/非 facebook)dev={dev_mongo_id}")
    base_message, api, dev_id = prepared

    account_ids = [
        a if a.startswith("act_") else f"act_{a}" for a in account_ids
    ] or _list_account_ids(msg, base_message)
    if not account_ids:
        raise SystemExit(f"dev={dev_id} 没有可补的 account")

    _probe_ads_api_access_tier(api, account_ids)
    base_message["ads_api_access_tier"] = api.api.ads_api_access_tier
    logger.warning(
        "[manual_backfill] dev_id=%s tier=%s 户=%d 天=%d (%s ~ %s)",
        dev_id, base_message["ads_api_access_tier"], len(account_ids), len(days),
        date_start, date_end,
    )

    # 同 dev 内共享 url→线 / 线→(placer, dept) 的 mongo 查询缓存,跨小时/跨天/跨户复用
    shared_caches: tuple = ({}, {})
    results: List[Dict[str, Any]] = []
    for aid in account_ids:
        for day in days:
            logger.warning("[manual_backfill] 开始 account=%s day=%s", aid, day)
            try:
                r = _backfill_one(
                    aid, day, base_message, api,
                    include_frequency, include_breakdowns, hourly_include_video,
                    overwrite_existing, shared_caches,
                )
            except Exception as e:
                logger.exception("[manual_backfill] account=%s day=%s 失败", aid, day)
                r = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            results.append({"account_id": aid, "day": day, **r})

    ok = [r for r in results if r["ok"] and not r.get("error")]
    partial = [r for r in results if r["ok"] and r.get("error")]
    bad = [r for r in results if not r["ok"]]
    print(f"\n[manual_backfill] 完成:成功 {len(ok)} / 部分 {len(partial)} / 失败 {len(bad)}")
    for r in results:
        mark = "OK  " if r["ok"] and not r.get("error") else ("PART" if r["ok"] else "FAIL")
        print(
            f"  [{mark}] {r['account_id']} {r['day']} "
            f"hour_rows={r.get('hour_rows', 0)}({r.get('hours', '-')}) "
            f"day_rows={r.get('day_rows', 0)}"
            + (f" note={r['note']}" if r.get("note") else "")
            + (f" err={r['error']}" if r.get("error") else "")
        )


if __name__ == "__main__":
    init("manual_backfill_insights")
    main(
        # accounts._id (系统开发者) 或 personal_accounts._id (个号) 字符串
        dev_mongo_id="122275126790594890",
        # False -> accounts (系统开发者) ; True -> personal_accounts (个号授权)
        is_personal=True,
        # 要补的户,act_ 前缀可带可不带;[] = 该 dev 名下全部户(读 mongo 缓存)
        account_ids=["act_1013047744385124"],
        # 账户本地日,闭区间,须早于今天(中国日期)
        date_start="2026-07-27",
        date_end="2026-07-30",
        # 写生产/测试库不在这里配:启动时用 DEPLOY_ENV=prod / test 选(见模块 docstring)
        # 对齐 review:整日拉取时是否带 frequency(9 份报告/户/天)和 age_gender breakdown
        include_frequency=True,
        include_breakdowns=True,
        # 小时报告是否带 video 字段;若 FB 报字段与 hourly breakdown 不兼容,关掉重跑
        hourly_include_video=False,
        # 默认只补目标库里缺的小时槽/缺定稿;True = 无视已有数据整天强制重写
        overwrite_existing=False,
    )
