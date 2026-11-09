"""扫 redis 里 ad_sync_new 的 dev 级状态。两部分:

1. 开头一次性快照:
   - 每个有任务的 dev_id(account_queue:{dev_id} LLEN > 0)
   - 是否被某个 worker 进程 claim 住(dev_claim:{dev_id} 存在 → claimed)
   - 「有任务但没 claim」就是积压信号:容器不够 / 进程崩了还没续接

2. 循环采样:account_queue 总数 + 每 30s 的处理速率 + 还有积压的 dev 数

用法:
  python -m tasks.ad_sync_new.scripts.check_dev_inflight
  Ctrl-C 退出
"""

import time
from datetime import datetime

from db.clients import redis_cli

from tasks.ad_sync_new.consts import REDIS_ACCOUNT_QUEUE_FMT, REDIS_DEV_CLAIM_FMT


SAMPLE_INTERVAL_SEC = 30   # 每 30s 采一次,1 分钟 2 次


def _scan_dev_ids(prefix: str) -> set:
    """扫一类 key,把 {prefix}{dev_id} 里的 dev_id 部分抽出来,返回 set。"""
    pattern = prefix + "*"
    out = set()
    for key in redis_cli.scan_iter(match=pattern, count=500):
        key_s = key.decode() if isinstance(key, bytes) else key
        out.add(key_s[len(prefix):])
    return out


def _sample_queue():
    """扫 account_queue:* 的全部 key,返回 (dev_id → llen, total)。"""
    prefix = REDIS_ACCOUNT_QUEUE_FMT.split("{")[0]
    pattern = prefix + "*"
    out = {}
    for key in redis_cli.scan_iter(match=pattern, count=500):
        key_s = key.decode() if isinstance(key, bytes) else key
        try:
            llen = int(redis_cli.llen(key_s))
        except Exception:
            continue
        out[key_s[len(prefix):]] = llen
    return out, sum(out.values())


def _print_claim_snapshot_once():
    """开头打一次快照:dev_id 有任务 vs 是否被 claim。"""
    claim_prefix = REDIS_DEV_CLAIM_FMT.split("{")[0]

    queue_data, queue_total = _sample_queue()
    pending = {k for k, v in queue_data.items() if v > 0}
    claimed = _scan_dev_ids(claim_prefix)

    all_devs = sorted(pending | claimed)
    pending_and_claimed = pending & claimed
    pending_no_claim = pending - claimed       # 有活没人接 = 积压信号
    claimed_no_pending = claimed - pending     # worker 守着空 dev(等 idle 释放)

    print()
    print("=== dev claim/queue 快照(开头打一次)===")
    print(f"  queue total = {queue_total}  | pending devs(有任务)= {len(pending)}  | claimed devs(被 worker 占)= {len(claimed)}")
    print(f"  既 pending 又 claimed(正在干)= {len(pending_and_claimed)}")
    print(f"  pending 但无 claim(积压,无 worker)= {len(pending_no_claim)}")
    print(f"  claimed 但 queue 空(worker 等 idle 释放)= {len(claimed_no_pending)}")
    print()
    print(f"  {'queue_len':>9}  {'claimed':>7}  dev_id")
    for dev_id in all_devs:
        q = queue_data.get(dev_id, 0)
        c = "Y" if dev_id in claimed else " "
        print(f"  {q:>9d}  {c:>7s}  {dev_id}")
    print()


def main():
    _print_claim_snapshot_once()

    prev_total = None
    prev_ts = None
    print("=== account_queue 循环采样 ===")
    delta_header = f"Δ/{SAMPLE_INTERVAL_SEC}s"
    print(f"{'time':>8}  {'total':>8}  {delta_header:>10}  {'rate/min':>10}  {'pending_devs':>12}  {'claimed':>7}")
    while True:
        now = time.time()
        data, total = _sample_queue()
        pending_devs = sum(1 for v in data.values() if v > 0)
        claimed = len(_scan_dev_ids(REDIS_DEV_CLAIM_FMT.split("{")[0]))

        if prev_total is None:
            delta_str = "-"
            rate_str = "-"
        else:
            delta = prev_total - total            # queue 是下降的,delta 为正 = 处理掉多少
            elapsed_min = (now - prev_ts) / 60.0
            rate = delta / elapsed_min if elapsed_min > 0 else 0
            delta_str = f"{delta:+d}"
            rate_str = f"{rate:.0f}"

        ts_str = datetime.now().strftime("%H:%M:%S")
        print(f"{ts_str:>8}  {total:8d}  {delta_str:>10}  {rate_str:>10}  {pending_devs:>12d}  {claimed:>7d}")

        prev_total = total
        prev_ts = now
        try:
            time.sleep(SAMPLE_INTERVAL_SEC)
        except KeyboardInterrupt:
            print("\n退出")
            return


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n退出")
