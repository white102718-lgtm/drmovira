"""手动推一条 dev message 到 `ad_sync_new:dev_queue`,让 dispatcher 容器消费。

跟生产 producer 干的事一样,只是只推 1 条(指定 dev_mongo_id)。
**真发消息,真的会触发整条链路**:dispatcher 抢账户锁 + 推 account_queue,
account_consumer 容器接着拉数据写 doris。

用法:
  cd schedulers
  python -m tasks.ad_sync_new.scripts.push_dev
"""

import json
from datetime import datetime, timedelta, timezone

from conf.log_conf import init
from db.clients import redis_cli
from tasks.ad_sync_new.consts import REDIS_DEV_QUEUE, ProducerMethod


def main(
    dev_mongo_id: str,
    date: str = None,
    review: bool = False,
    is_personal: bool = False,
):
    if date is None:
        date = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H")
    msg = {
        "_id": dev_mongo_id,
        "date": date,
        "review": review,
        "type": (
            ProducerMethod.PERSONAL_PRODUCER.value
            if is_personal
            else ProducerMethod.PRODUCER.value
        ),
    }
    redis_cli.rpush(REDIS_DEV_QUEUE, json.dumps(msg))
    print(f"pushed → {REDIS_DEV_QUEUE}: {msg}")


if __name__ == "__main__":
    init("push_ad_sync_new_dev")
    main(
        # accounts._id (PRODUCER) 或 personal_accounts._id (PERSONAL_PRODUCER) 字符串
        dev_mongo_id="69faf7fd985021c636b177ec",
        # "YYYY-MM-DD HH" 上海时;None = 当前上海整点
        date="2026-05-14 16",
        # 整日回填 (review=True) vs 当前小时增量 (False)
        review=False,
        # False -> accounts (标准开发者) ; True -> personal_accounts (个号授权)
        is_personal=False,
    )
