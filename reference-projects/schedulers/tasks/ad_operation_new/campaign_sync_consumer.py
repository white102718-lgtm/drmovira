"""操作成功后的系列定向同步消费者。

op_consumer 成功后只推 {account_id, campaign_id, dev_app} 进队列,本进程消费并调
sync_campaign_to_doris,拉数优先用该账户的企业(系统)开发者,找不到才退回操作时的
dev_app。与操作执行分进程,FB 配额退避(一睡 2~10 分钟)不再拖住操作线程。
失败只记日志,半点全量同步兜底。

FB 变更异步生效期间 effective_status 是 IN_PROCESS(面板会闪"处理中"),
撞到时本轮不写,带 not_before/attempts 推回队列延迟重试,重试耗尽交全量兜底。
"""

import json
import logging
import time

from conf.log_conf import init
from db.clients import redis_cli_3 as operation_redis
from tasks.ad_operation_new.common import AD_OP_CAMPAIGN_SYNC_QUEUE_KEY
from tasks.ad_operation_new.storage import get_dev_app_by_account_id
from tasks.ad_sync_new.campaign_sync import sync_campaign_to_doris

init("campaign_sync_consumer")

IDLE_SLEEP_SEC = 3
RETRY_DELAY_SEC = 30
MAX_ATTEMPTS = 3


def _process(message: dict) -> bool:
    """返回是否需要重试(撞到 IN_PROCESS)。"""
    account_id = str(message["account_id"])
    campaign_id = message["campaign_id"]
    dev_app = get_dev_app_by_account_id(
        account_id.removeprefix("act_")
    ) or message.get("dev_app")
    if not dev_app:
        logging.error(f"找不到可用开发者, 跳过: account_id={account_id} campaign_id={campaign_id}")
        return False
    return sync_campaign_to_doris(dev_app, account_id, campaign_id)


def campaign_sync_consumer():
    logging.info("campaign_sync_consumer 启动")
    while True:
        raw = operation_redis.lpop(AD_OP_CAMPAIGN_SYNC_QUEUE_KEY)
        if raw is None:
            time.sleep(IDLE_SLEEP_SEC)
            continue
        try:
            message = json.loads(raw)
            if message.get("not_before", 0) > time.time():
                operation_redis.rpush(AD_OP_CAMPAIGN_SYNC_QUEUE_KEY, raw)
                time.sleep(IDLE_SLEEP_SEC)
                continue
            if _process(message):
                attempts = message.get("attempts", 0) + 1
                if attempts < MAX_ATTEMPTS:
                    message["attempts"] = attempts
                    message["not_before"] = time.time() + RETRY_DELAY_SEC
                    operation_redis.rpush(
                        AD_OP_CAMPAIGN_SYNC_QUEUE_KEY, json.dumps(message)
                    )
                else:
                    logging.warning(f"IN_PROCESS 重试耗尽, 交全量兜底: {message}")
        except Exception:
            raw_str = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
            logging.error(f"定向同步失败(半点全量兜底): {raw_str[:500]}", exc_info=True)


if __name__ == "__main__":
    campaign_sync_consumer()
