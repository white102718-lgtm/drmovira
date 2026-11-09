from datetime import datetime, timedelta

from conf.log_conf import init
from tasks.ad_sync_new.producer import producer as ad_sync_producer
from tasks.ad_sync_new.consts import ProducerMethod
from tasks.fb_business_sync.fb_business_sync import sync_fb_business_data
from tasks.ad_materials.ad_materials_sync import (write_ad_materials,
                                                  reuse_historical_unique_names,
                                                  log_unfilled_summary)
from tasks.ad_materials.asset_name_sync import sync_fb_asset_names
from tasks.check_ad_status.tech_department_fb_account_status import check_tech_department_fb_account_status
from tasks.check_ad_status.tech_department_pixel_status import check_tech_department_pixel_status
from tasks.check_ad_status.account_balance_alert import check_account_balance_alert
from tasks.ad_sync_new.backfill_ad_fields import backfill_ad_fields
from tasks.ad_sync_new.backfill_account_dsl import backfill_account_dsl
from tasks.ad_sync_new.agent_line_backfill.match_agent_line_daily import match_agent_line_daily
from tasks.ad_sync_new.agent_line_backfill.backfill_hourly_dept_from_daily import (
    backfill_hourly_dept_from_daily,
)
from tasks.erp_kpi_sync.erp_channel_sync import sync_erp_channel_to_doris
from tasks.erp_kpi_sync.erp_dept_sync import sync_erp_depts_to_mongo
from tasks.erp_kpi_sync.erp_user_sync import sync_erp_users_to_mongo
from tasks.erp_kpi_sync.f9_agent_line_performance_report import (
    push_f9_agent_line_performance_report,
)
from tasks.erp_kpi_sync.placer_daily_report import push_placer_daily_report
from tasks.feishu_sync.feishu_account_sync import sync_feishu_account_records
from utils.fb_utils import install_fb_usage_backoff

init("scheduler_main")
# scheduler cron 任务会调 FB SDK (ad_sync_producer 等), 装 sleep 退避保护账户配额
install_fb_usage_backoff(auto_sleep=True)

import logging
from apscheduler.executors.pool import ThreadPoolExecutor
from io import StringIO
from zoneinfo import ZoneInfo

from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.blocking import BlockingScheduler
from utils.common_util import handle_error

job_stores = {"default": MemoryJobStore()}
executors = {
    "default": ThreadPoolExecutor(max_workers=30),
}
job_defaults = {
    "coalesce": True,  # 不合并错过的任务
    "max_instances": 2,  # 每个任务最多同时运行2个实例
    "misfire_grace_time": 30,  # 错过30秒内的任务仍会执行
}

china_timezone = ZoneInfo("Asia/Shanghai")
scheduler = BlockingScheduler(
    jobstores=job_stores, executors=executors, job_defaults=job_defaults
)


def safe_task_wrapper(func, *args, **kwargs):
    """安全的任务包装器"""
    @handle_error(error_message=f"任务 {func.__name__} 执行失败", reraise=True)
    def _execute():
        logging.info(f"开始执行任务: {func.__name__}")
        result = func(*args, **kwargs)
        logging.info(f"任务执行完成: {func.__name__}")
        return result

    return _execute()


def _ad_materials_pipeline():
    """生产端一站式流水线: 库内 reuse → 把仍缺的入队下载 → 打印漏网摘要

    下载由独立的 ad_materials_fetch_worker / ad_creative_scrape_worker
    消费 Redis 队列完成,本流水线只生产消息,不耦合下载.
    入队带 SETNX 去重锁(6h TTL),允许本流水线高频运行而不重复入队.
    """
    reuse_historical_unique_names(hours=2, lookback_days=2)
    write_ad_materials(day=1)
    log_unfilled_summary(hours=6)


# ── 广告同步 (新版 ad_sync_new): tasks/ad_sync_new/producer.py
# producer 把 dev message 推到 redis `ad_sync_new:dev_queue`,
# dispatcher / account_consumer 是独立 docker-compose 容器,起来后阻塞在队列上消费。
# :00 / :30 各跑一次:写整点/日表(date 截到小时/天,:30 刷新当前整点行),
# 并派生半点桶写 ad_half_hour_detail。半点表靠 :00/:30 两次真实拉取得到两个累计快照。
scheduler.add_job(
    lambda: safe_task_wrapper(ad_sync_producer, method=ProducerMethod.PRODUCER),
    "cron",
    hour="*",
    minute="0,30",
    timezone=china_timezone,
    id="ad_sync",
)
scheduler.add_job(
    lambda: safe_task_wrapper(ad_sync_producer, method=ProducerMethod.PERSONAL_PRODUCER),
    "cron",
    hour="*",
    minute="0,30",
    timezone=china_timezone,
    id="ad_sync_personal",
)
def _run_review_producer(method, days_ago=1):
    """触发时再算"days_ago 天前中国日期 00",传给 producer。HH=00 是约定值,review
    处理时下游 effective_account_dt 会按账户 TZ 重算有效时刻;消息里保留 HourFormat
    主要是给 ad_sync_history.date / doris 字段格式一致用。
    producer 看到 china_date 的日期段早于今天 → 自动按 review 语义处理。"""
    target_day = (datetime.now(china_timezone).date() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
    return safe_task_wrapper(ad_sync_producer, method=method, china_date=f"{target_day} 00")


# 17:20:最西账户时区 UTC-9(America/Nome)的"昨天"在中国 17:00 才走完,更早拉是半天数据。
# 若以后出现更西的账户(如夏威夷 UTC-10),要相应后移。
scheduler.add_job(
    lambda: _run_review_producer(ProducerMethod.PRODUCER),
    "cron",
    hour="17",
    minute="20",
    timezone=china_timezone,
    id="ad_sync_day",
)
scheduler.add_job(
    lambda: _run_review_producer(ProducerMethod.PERSONAL_PRODUCER),
    "cron",
    hour="17",
    minute="20",
    timezone=china_timezone,
    id="ad_sync_personal_day",
)
# 05:20:t-4 归因回流(转化在归因窗口内持续更新,重拉刷新旧数据)。
# 与 17:20 的 t-1 岔开 12 小时,错峰占用 review 池。
scheduler.add_job(
    lambda: _run_review_producer(ProducerMethod.PRODUCER, days_ago=4),
    "cron",
    hour="5",
    minute="20",
    timezone=china_timezone,
    id="ad_sync_day_t4",
)
scheduler.add_job(
    lambda: _run_review_producer(ProducerMethod.PERSONAL_PRODUCER, days_ago=4),
    "cron",
    hour="5",
    minute="20",
    timezone=china_timezone,
    id="ad_sync_personal_day_t4",
)
# 11:10:t-2 归因回流。与 05:20 的 t-4、17:20 的 t-1 错开，
# 同时避开 :00/:30 实时成效同步、:20 素材任务和 :40 资产同步。
scheduler.add_job(
    lambda: _run_review_producer(ProducerMethod.PRODUCER, days_ago=2),
    "cron",
    hour="11",
    minute="10",
    timezone=china_timezone,
    id="ad_sync_day_t2",
)
scheduler.add_job(
    lambda: _run_review_producer(ProducerMethod.PERSONAL_PRODUCER, days_ago=2),
    "cron",
    hour="11",
    minute="10",
    timezone=china_timezone,
    id="ad_sync_personal_day_t2",
)
# 定时任务（fb_business_sync.py）：查询开发者，推送到 fb:business:sync:queue
scheduler.add_job(
    lambda: safe_task_wrapper(sync_fb_business_data),
    "cron",
    hour="*",
    minute="40",
    timezone=china_timezone,
    id="fb_business_sync",
)
# 素材流水线: 每小时 :20 跑 reuse → enqueue → summary
# :20 错开整点的 ad_sync_producer (consumer 写 Doris 通常在 :00 后约 20 分钟才结束)
scheduler.add_job(
    lambda: safe_task_wrapper(_ad_materials_pipeline),
    "cron",
    hour="*",
    minute="20",
    timezone=china_timezone,
    id="ad_materials_pipeline",
)
# 监控账户状态
scheduler.add_job(
    safe_task_wrapper,
    "cron",
    hour="*",
    minute="0",
    timezone=china_timezone,
    id="job_check_tech_department_fb_account_status",
    kwargs={"func": check_tech_department_fb_account_status},
)
# 监控技术部代理线像素状态: fb_pixels.is_unavailable=true 时按优化师分组发飞书,
# 每个像素只推一次(redis set 永不过期, 重推需手动 SREM)
scheduler.add_job(
    safe_task_wrapper,
    "cron",
    hour="*",
    minute="0",
    timezone=china_timezone,
    id="job_check_tech_department_pixel_status",
    kwargs={"func": check_tech_department_pixel_status},
)
# 账户余额预警: 每小时查当前整点 技术部 户的剩余可投放额度(spend_cap-amount_spent),
# 低于在投预算(SUM cam_budget)时按投手分组发飞书群机器人 webhook。
# :29 跑 —— 错开 :00 整点拉取(consumer 约 :25 写完当前整点行),确保读到当前整点数据
scheduler.add_job(
    lambda: safe_task_wrapper(check_account_balance_alert),
    "cron",
    hour="*",
    minute="29",
    timezone=china_timezone,
    id="account_balance_alert",
)
# account_dsl 回填: Mongo fb_ad_accounts → hourly/daily 当前整点 account 行
# :27 跑 —— consumer ~:25 写完当前整点行之后、:29 余额预警读 account_dsl 之前
scheduler.add_job(
    lambda: safe_task_wrapper(backfill_account_dsl),
    "cron",
    hour="*",
    minute="27",
    timezone=china_timezone,
    id="backfill_account_dsl",
)
# 回填原帖广告的 landing_url 及代理线信息，每7分钟执行
scheduler.add_job(
    lambda: safe_task_wrapper(backfill_ad_fields),
    "interval",
    minutes=10,
    timezone=china_timezone,
    id="backfill_landing_url",
)
# review 同步(08:33)会全量重写00:00记录导致已回填字段被覆盖，需在其后用大窗口重新回填
# TODO 修改写入数据时, 如果字段为None则不写入这些字段, 防止更新时覆盖之前有值的字段(代理线平台部门url
scheduler.add_job(
    lambda: safe_task_wrapper(backfill_ad_fields, lookback_hours=30),
    "cron",
    hour="9",
    minute="30",
    timezone=china_timezone,
    id="backfill_landing_url_after_review",
)
def _agent_line_backfill_pipeline():
    """先按 campaign_name/URL 匹配回填 ad_daily_detail 的代理线,再用 daily 结果回填 ad_hourly_detail。"""
    today = datetime.now(china_timezone).date()
    start = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")
    match_agent_line_daily(start_date=start, end_date=end)
    backfill_hourly_dept_from_daily(start_date=start, end_date=end)


# 代理线回填: 每天 0 点跑过去 7 天
scheduler.add_job(
    lambda: safe_task_wrapper(_agent_line_backfill_pipeline),
    "cron",
    hour="0",
    minute="0",
    timezone=china_timezone,
    id="agent_line_backfill",
)
# 每两小时从 ERP 增量同步渠道(及其户的 account_ids)到 Doris fb_ad_channel
scheduler.add_job(
    lambda: safe_task_wrapper(sync_erp_channel_to_doris),
    "interval",
    hours=2,
    timezone=china_timezone,
    id="erp_channel_sync",
)
# 指定项目代理线成效：按北京时间整点后 30 分钟执行，确保整点成效已落库。
scheduler.add_job(
    lambda: safe_task_wrapper(push_f9_agent_line_performance_report),
    "cron",
    hour="0,3,6,9,12,15,18,21",
    minute="30",
    timezone=china_timezone,
    id="f9_agent_line_performance_report",
)
# 投手日报 Excel: 昨日数据按投手拆表推给本人飞书。
# 14:00 出初版(此时最西的户是 US/Eastern,昨天已走完);17:50 在 17:20 的 t-1 review
# 重拉回流之后再发一版最终数。
scheduler.add_job(
    lambda: safe_task_wrapper(push_placer_daily_report),
    "cron",
    hour="14",
    minute="0",
    timezone=china_timezone,
    id="placer_daily_report",
)
scheduler.add_job(
    lambda: safe_task_wrapper(push_placer_daily_report),
    "cron",
    hour="17",
    minute="50",
    timezone=china_timezone,
    id="placer_daily_report_after_review",
)
# 12:10 推送 T-2 回流日报，为 11:10 的 T-2 review 重拉预留一小时同步时间。
scheduler.add_job(
    lambda: safe_task_wrapper(push_placer_daily_report, days_ago=2),
    "cron",
    hour="12",
    minute="10",
    timezone=china_timezone,
    id="placer_daily_report_t2_after_review",
)
# FB 原始素材名: 给成效表里 unique_name 仍为空的 ad 补它用的图片/视频在 FB 素材库
# 里的原始上传文件名,写 mongo ad_asset_names。
# 一天两次: 取的是首次快照,晚几小时补上没影响,而它跟成效同步共用同一批
# app/token 配额,跑得越勤越挤占成效。
# 10:45 / 22:45 —— 跟 05:20、17:20 两次 review 全量重拉(FB 配额大头)各错开 5 小时;
# :45 避开 :00/:30 成效拉取(consumer 约 :25 写完)和 :20/:27/:29/:40 的其它任务,
# 也在 :20 素材管道回填 unique_name 之后,拿到的是最新的"素材名已知"状态。
# max_instances=1: 一轮没跑完不开下一轮(去重让重跑幂等,但重叠会白打 FB)。
scheduler.add_job(
    lambda: safe_task_wrapper(sync_fb_asset_names),
    "cron",
    hour="10,22",
    minute="45",
    timezone=china_timezone,
    id="fb_asset_name_sync",
    max_instances=1,
)
# 每 10 分钟把 ERP dept_id=100 子树部门全量对账到 mongo plat.department_config
scheduler.add_job(
    lambda: safe_task_wrapper(sync_erp_depts_to_mongo),
    "cron",
    minute="*/10",
    timezone=china_timezone,
    id="erp_dept_sync",
)
# 每 10 分钟把 ERP 用户全量对账到 mongo user.user(新增/更新/删除,ERP 为唯一真源)
scheduler.add_job(
    lambda: safe_task_wrapper(sync_erp_users_to_mongo),
    "cron",
    minute="*/10",
    timezone=china_timezone,
    id="erp_user_sync",
)
# 飞书「MP媒介资料表」四张工作表的在用账户 → mongo plat.feishu_account_used_record。
# 表格靠人工维护,只在上班时间跑(跳过 13 点午休);全量拉一轮约 35 秒。
scheduler.add_job(
    lambda: safe_task_wrapper(sync_feishu_account_records),
    "cron",
    hour="10,11,12,14,15,16,17,18,19,20",
    minute="0",
    timezone=china_timezone,
    id="feishu_account_sync",
    max_instances=1,
)

if __name__ == "__main__":
    buffer = StringIO()
    scheduler.print_jobs(out=buffer)
    jobs_output = buffer.getvalue()
    buffer.close()
    logging.warning(f"全部定时任务\n{jobs_output}")
    scheduler.start()
