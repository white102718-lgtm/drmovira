"""端到端本地调试 ad_sync_new:**指定 dev + 指定单个 account**,
绕过 redis / dispatcher / account_consumer 主循环,直接调 _process_one_account。

跟 debug_run_one_dev.py 的区别:
  - dev 脚本:dispatcher → DevWorker 完整新架构链路
  - 本脚本:绕过 redis 直接调业务核心,最快验证单户问题(比如 17/2446079)

不写 ad_sync_history(用 fake history_id 占位),不抢 account_lock,不写 progress。
但 fetch_all → transform → write_to_doris 是真跑、真写 doris。

用法:
  cd schedulers
  python -m tasks.ad_sync_new.scripts.debug_run_one_account
"""

from datetime import datetime, timedelta, timezone

from bson import ObjectId
from pyinstrument import Profiler

from conf.log_conf import init
from tasks.ad_sync_new.account_consumer import _process_one_account
from tasks.ad_sync_new.consts import ProducerMethod
from tasks.ad_sync_new.dispatcher import (
    _probe_ads_api_access_tier,
    prepare_base_message,
)


def main(
    dev_mongo_id: str,
    account_id: str,
    date: str = None,
    is_personal: bool = False,
):
    if date is None:
        date = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H")

    msg = {
        "_id": dev_mongo_id,
        "date": date,
        "type": (
            ProducerMethod.PERSONAL_PRODUCER.value
            if is_personal
            else ProducerMethod.PRODUCER.value
        ),
    }
    fake_history_id = str(ObjectId())   # 占位:不写 ad_sync_history
    prepared = prepare_base_message(msg, history_id=fake_history_id)
    if prepared is None:
        raise SystemExit(f"prepare_base_message 失败 dev_mongo_id={dev_mongo_id}")
    base_message, api, dev_id = prepared

    # 跟 dispatch_dev 一致:派发前探一次 tier 塞进 base_message,否则 pipeline 永远
    # 按 dev tier 路径跑(pipeline.py:286),复现的不是该 dev 的真实路径。
    _probe_ads_api_access_tier(api, [account_id])
    base_message["ads_api_access_tier"] = api.api.ads_api_access_tier

    print(
        f"[debug_run_one_account] dev_id={dev_id} account={account_id} "
        f"date={date} tier={base_message['ads_api_access_tier']} "
        f"history_id={fake_history_id}"
    )

    profiler = Profiler(interval=0.001, async_mode="disabled")
    profiler.start()
    try:
        result = _process_one_account(account_id, base_message, api)
    finally:
        profiler.stop()
        print(profiler.output_text(unicode=True, color=True, show_all=True))

    print("[debug_run_one_account] result:")
    print(f"  ok        = {result['ok']}")
    print(f"  rows      = {result['rows']}")
    print(f"  elapsed_s = {result['elapsed_sec']:.1f}")
    if not result["ok"]:
        print(f"  error     =\n{result['error']}")


if __name__ == "__main__":
    init("debug_ad_sync_new_one_account")
    main(
        # accounts._id (PRODUCER) 或 personal_accounts._id (PERSONAL_PRODUCER) 字符串
        dev_mongo_id="122172182876931408",
        # 带 "act_" 前缀的 FB 账户 id
        account_id="act_1758821595102531",
        # 上海时;None = 当前上海整点(hourly)。"YYYY-MM-DD HH" 日期段早于今天 =
        # review 整日回填(由 consts.is_review 自动判定,无单独 review 开关)。
        date="2026-06-05 13",
        is_personal=True,
    )
