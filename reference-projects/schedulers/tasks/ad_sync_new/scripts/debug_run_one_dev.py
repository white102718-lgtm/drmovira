"""端到端本地调试 ad_sync_new:**指定 dev,走完整 prod 链路**(dispatcher 推消息
到 redis account_queue,然后本进程实例化 DevWorker 消费)。

跟 debug_run_one_account.py 的区别:
  - account 脚本绕过 redis 直跑单户,验证业务逻辑
  - 本脚本走完整新架构(SETNX claim、ThreadPoolExecutor、progress 写 mongo)

⚠ 会跟生产 account_consumer 抢同一个 dev_claim。本地跑前先确保生产没在跑同一个
   dev_id,或者用只本地有数据的测试 dev。

用法:
  cd schedulers
  python -m tasks.ad_sync_new.scripts.debug_run_one_dev
"""

from pyinstrument import Profiler

from conf.log_conf import init
from tasks.ad_sync_new import account_consumer
from tasks.ad_sync_new.dispatcher import run_dev_locally

_orig_process_one_account = account_consumer._process_one_account


def _profiled_process_one_account(account_id, base_message, api):
    # Profiler 只采样所在线程,所以在 account 子线程内包业务核心,每户一份报告
    profiler = Profiler(interval=0.001, async_mode="disabled")
    profiler.start()
    try:
        return _orig_process_one_account(account_id, base_message, api)
    finally:
        profiler.stop()
        print(f"--- pyinstrument account={account_id} ---")
        print(profiler.output_text(unicode=True, color=True, show_all=True))


account_consumer._process_one_account = _profiled_process_one_account


if __name__ == "__main__":
    init("debug_ad_sync_new_one_dev")
    run_dev_locally(
        # accounts._id (PRODUCER) 或 personal_accounts._id (PERSONAL_PRODUCER) 字符串
        dev_mongo_id="1009317945082635",
        # "YYYY-MM-DD HH" 上海时;None = 当前上海整点
        date="2026-06-11 11",
        # False -> accounts(标准开发者); True -> personal_accounts(个号)
        is_personal=True,
    )
