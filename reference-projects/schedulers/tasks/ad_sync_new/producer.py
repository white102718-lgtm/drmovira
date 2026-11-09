"""ad_sync_new 的 producer:scan mongo accounts / personal_accounts → 推 dev
message 到 redis 队列 `ad_sync_new:dev_queue`,跟老 ad_sync.producer 隔离。

消息形状:
  {"_id": str, "date": "YYYY-MM-DD HH:MM"(hourly 到半点)或"YYYY-MM-DD HH"(review)上海时, "type": "producer"|"personal_producer"}

review / hourly 不再用单独的布尔字段区分,**完全由 date 串隐含**:
  - hourly 推的 china_date 是当前中国半点(:00 / :30)→ 日期段 == 今天。半点粒度
    让同一小时两次调度成为不同 date 串,history 去重把它们当独立 run;数据层经
    `consts.effective_account_dt` 取账户本地半点,hourly/daily 表在落库前才截粒度。
  - review 推的 china_date 是用户选中的"过去那天"(只到日期级)→ 日期段 < 今天
  下游用 `consts.is_review(date)` 现场推断即可。
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from db.clients import mongo_client, redis_cli
from utils.common import MinuteFormat
from utils.common_util import handle_error

from tasks.ad_sync_new.consts import REDIS_DEV_QUEUE, ProducerMethod


logger = logging.getLogger(__name__)


@handle_error(error_message="ad_sync_new 生产者运行报错")
def producer(method: ProducerMethod, china_date: str = None) -> None:
    """扫开发者表 → 推 dev message。
    Args:
        method: ProducerMethod.PRODUCER (accounts) 或 PERSONAL_PRODUCER (personal_accounts)
        china_date: 不传 = 当前中国整点(hourly);传"YYYY-MM-DD"(过去那天)= review。
            自动 review 判定见 `consts.is_review`。
    """
    logger.warning("[ad_sync_new] 生产者启动 method=%s china_date=%s", method, china_date)

    if china_date is None:
        # date 到半点粒度("YYYY-MM-DD HH:00"/":30"):同一小时的 :00 / :30 两次调度
        # 是不同 date 串,history 去重就能像跨小时一样把半点当独立 run。数据层取
        # 账户本地半点(consts.effective_account_dt),hourly/daily 落库前才截粒度。
        now_cn = datetime.now(timezone(timedelta(hours=8)))
        slot_minute = 30 if now_cn.minute >= 30 else 0
        china_date = now_cn.replace(
            minute=slot_minute, second=0, microsecond=0
        ).strftime(MinuteFormat)

    if method == ProducerMethod.PRODUCER:
        cursor = list(
            mongo_client["accounts"].find(
                {"status": 1, "account_usage.insights_pull": True},
                projection={"_id": 1},
            )
        )
        _type = ProducerMethod.PRODUCER.value
    elif method == ProducerMethod.PERSONAL_PRODUCER:
        cursor = list(
            mongo_client["personal_accounts"].find(
                {"status": True}, projection={"_id": 1}
            )
        )
        _type = ProducerMethod.PERSONAL_PRODUCER.value
    else:
        raise ValueError(f"unknown ProducerMethod: {method}")

    pushed = 0
    for row in cursor:
        message = {
            "_id": str(row["_id"]),
            "date": china_date,
            "type": _type,
        }
        redis_cli.rpush(REDIS_DEV_QUEUE, json.dumps(message))
        pushed += 1
        logger.info("[ad_sync_new] 推送 dev message: %s", message)

    logger.warning(
        "[ad_sync_new] 生产者完成 method=%s,共推送 %d 个 dev 到队列 %s",
        method, pushed, REDIS_DEV_QUEUE,
    )


if __name__ == "__main__":
    from conf.log_conf import init
    init("ad_sync_new_producer")
    # personal 先发,system_user(PRODUCER)后发 —— 抢账户锁时 personal 优先
    for day in (
        "2026-07-04", "2026-07-05", "2026-07-06", "2026-07-07",
        "2026-07-08", "2026-07-09", "2026-07-10", "2026-07-11",
    ):
        producer(method=ProducerMethod.PERSONAL_PRODUCER, china_date=day)
        producer(method=ProducerMethod.PRODUCER, china_date=day)
