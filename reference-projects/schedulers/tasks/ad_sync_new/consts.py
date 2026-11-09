"""ad_sync_new 用到的常量集中点 —— redis key / enum / 其它共享配置。

跟老 tasks/ad_sync/ 完全隔离:
  - redis key 不共用 (`ad_sync_new:*` vs `ad:sync:hourly*` / `fb_sync:*` 老 key)
  - 新 producer / dispatcher / account_consumer 进程互不影响,可灰度

分布式拓扑(改造后):
  producer ──rpush──▶ ad_sync_new:dev_queue
                          │ blpop
                          ▼
                     consumer.py (dispatcher)
                          │  1. _load_dev + _list_account_ids
                          │  2. 每个 account 抢 ad_sync_new:account_lock:{aid}
                          │  3. SET ad_sync_new:dev_payload:{history_id}
                          │  4. RPUSH ad_sync_new:account_queue:{dev_id} × N
                          ▼
                  account_consumer.py × N (1 dev / 进程,多容器)
                          │  SCAN account_queue:* 发现非空 queue 后 SETNX dev_claim:{dev_id}
                          │  ThreadPoolExecutor(max_workers=50) 并发处理该 dev 的 account_queue
                          │  LPOP ad_sync_new:account_queue:{dev_id}
                          │  跑 _process_one_account
                          │  worker idle 退出时给当前 history_id 写 COMPLETED
                          ▼
                       doris / mongo
"""

from datetime import datetime, timedelta, timezone
from enum import Enum
from zoneinfo import ZoneInfo

from db.redis_client import REDIS_DB0_POOL_SIZE
from utils.common import HourFormat, MinuteFormat
from utils.fb_utils import resolve_tz


# ── redis 队列 ───────────────────────────────────────────────────────────────
# producer 推 dev 维度消息的入口队列(沿用旧名,与老系统隔离)
REDIS_DEV_QUEUE = "ad_sync_new:dev_queue"  # [LIST] dev 维度入队:producer → dispatcher

# 账户级二级队列:每个 dev 一条独立 list(Defined Shards 公平模型,
# 参考 palkan/faqueue 与 myui/fairque)。worker 通过 SCAN match=account_queue:*
# 发现非空 queue → SETNX dev_claim 抢锁,1 dev / 进程。
# LPOP 到空 redis 自动删 key,所以 SCAN 出来的都是有任务的。
REDIS_ACCOUNT_QUEUE_FMT = "ad_sync_new:account_queue:{dev_id}|{date}"  # [LIST] 单 (dev, date) 的 account 子队列:dispatcher → worker

# 账户互斥锁:防止同一个 FB account_id 同时被两个 dev 抓,共享同一份 BUC quota
# 会互相拖累(参考老 fb_account_consumer_async 的 fb_sync:account_lock 模式)。
REDIS_ACCOUNT_LOCK_FMT = "ad_sync_new:account_lock:{account_id}|{date}"  # [STRING+TTL] 单 (account, date) 互斥锁,跨 dev 抢占
# TTL 兜底:worker 死了锁也会自动过期,后续 dispatcher 可以重新抢。
# 单账户上限 ~ 账号 kill 阈值(3600s) + auto_sleep 退避(600s) + 余量。
ACCOUNT_LOCK_TTL_SEC = 2 * 3600

# 单 dev 同时跑 account 上限。每个 worker 线程占一条 db0 redis 连接,
# 所以锁死等于连接池大小,线程数不能超过它。
DEV_INFLIGHT_CAP = REDIS_DB0_POOL_SIZE

# 线程数按户量动态:threads = clamp(MIN + 户数 // PER_ACCOUNTS, MIN, DEV_INFLIGHT_CAP)。
# 100 户起步 ~44,2000 户打到 cap 120(PER=25 ⇒ 2000 户即到 120)。
DEV_THREADS_MIN = 40
DEV_THREADS_PER_ACCOUNTS = 25

# 单 dev 独占锁:一个 dev_id 同时只允许一个 account_consumer 进程 claim,通过
# SETNX + TTL 实现。worker 进程启动后 SCAN 非空 account_queue,挑一个 dev claim 住,
# 然后进程内 ThreadPoolExecutor(DEV_INFLIGHT_CAP) 并发处理该 dev 的 account_queue。
# 进程退出 / 异常崩了:claim 自动过期(TTL),下个 worker 进程接管。
REDIS_DEV_CLAIM_FMT = "ad_sync_new:dev_claim:{dev_id}|{date}"  # [STRING+TTL] 单 (dev, date) 独占锁,1 进程 = 1 (dev, date)
DEV_CLAIM_TTL_SEC = 70        # claim 不刷新多久过期 —— 进程崩后下个 worker 接管的最坏延迟 = TTL + IDLE_SLEEP_SEC
DEV_CLAIM_HEARTBEAT_SEC = 20  # heartbeat 间隔:每 20s 刷一次 claim 的 TTL(TTL 的 ~1/3,留足续期窗口)
DEV_IDLE_RELEASE_SEC = 180    # 队列连续空多久后释放 claim 退出,等下个调度重新 claim

# review 回填 per-dev 串行锁(不带 date):同一 dev 的多个历史日期同时只放一个跑,
# 跨 dev 不互斥可并行。claim 时抢、跟 claim 同寿命(心跳续期 + 退出释放)。
REDIS_REVIEW_DEV_LOCK_FMT = "ad_sync_new:review_dev_lock:{dev_id}"  # [STRING+TTL]

# dispatcher 把 dev 完整 base_message(凭据 + history 元数据)写到这里,
# account msg 只携带 history_id 引用 —— 避免每条账户消息体里都塞一份巨大的 dev 凭据。
# worker 用 in-process 缓存命中后不再回 redis。
# TTL 在 dispatcher 里动态算:到下个中国整点 -1s,确保下次 cron 触发前消失,
# 不会让旧 history 的 payload 跟新一次 dispatch 并存。
REDIS_DEV_PAYLOAD_FMT = "ad_sync_new:dev_payload:{history_id}"  # [STRING-JSON+TTL] 单 history 完整 base_message(凭据)
# review 回填的 payload 要等"同 dev 前面的天"串行跑完才被消费,远超 hourly 的
# 1~2h 节奏;给 48h 兜底防它在排队时过期。跑完即由 _finalize_history 删除,不会真占满。
REVIEW_PAYLOAD_TTL_SEC = 48 * 3600

# 单 (dev, day) 的"最新 history_id"指针:dispatcher 每次推完账户消息就更新成本次
# history_id。worker 据此把进度只写到最新 history —— 跨整点时旧 history 立即停更、
# 写 ABORT 收尾,不再被积压消息持续刷成 STARTED。
REDIS_DEV_LATEST_HISTORY_FMT = "ad_sync_new:dev_latest_history:{dev_id}|{date}"  # [STRING+TTL]


# ── producer 入口模式 ────────────────────────────────────────────────────────
class ProducerMethod(str, Enum):
    """跟老 ad_sync.ProducerMethod 同名同语义,在新系统里独立定义,避免引用老代码。

    - PRODUCER:扫 mongo `accounts` 集合(标准开发者)
    - PERSONAL_PRODUCER:扫 mongo `personal_accounts` 集合(个号授权)
    """

    PRODUCER = "producer"
    PERSONAL_PRODUCER = "personal_producer"


_CHINA_TZ = timezone(timedelta(hours=8))
_SHANGHAI = ZoneInfo("Asia/Shanghai")


def date_prefix(china_date: str) -> str:
    """取 china_date 的日期段(``"YYYY-MM-DD HH"`` 或 ``"YYYY-MM-DD"`` 都行)。

    给 redis lock / queue / claim 键 + ad_sync_history 去重 用 —— 颗粒度统一到
    "天",一天内同 dev 同时只能跑一个,不同天能并发。
    """
    return china_date.split(" ")[0]


def is_review(china_date: str) -> bool:
    """根据 china_date 的日期段是否早于"今天中国日期"自动判定 review。

    - hourly producer 推的 china_date 永远是当前中国整点 → 日期段 == 今天 → False
    - review producer 推的 china_date 是用户选中的 *过去* 那天 → 日期段 < 今天 → True

    边界情况:hourly 在凌晨 00:00 推 ``"YYYY-MM-DD 00"``,日期段 == 今天 → 非 review,
    走正常 hourly TZ 转换路径(在跨 TZ 账户上的语义跟之前完全一致)。
    """
    return date_prefix(china_date) < datetime.now(_CHINA_TZ).strftime("%Y-%m-%d")


def _floor_half_hour(dt: datetime) -> datetime:
    return dt.replace(minute=30 if dt.minute >= 30 else 0, second=0, microsecond=0)


def effective_account_dt(china_date: str, tz_name: str) -> datetime:
    """账户本地的"数据有效时刻",恒为精确半点(带 tzinfo)。全链路带着它走,
    各表粒度(小时/日)到 doris_writer 落库前才截 —— 中途不得经中国时间字符串
    截断回传:半小时时区(如 UTC+5:30)会把标签错移 30~60 分钟。

    - **hourly**(`is_review=False`):中国半点换算成账户本地时刻,向下取半点。
    - **review**(`is_review=True`):用户填的是 target 那天,数据截止点 = 账户本地
      次日 00:00(前一天的定稿槽);若该截止时刻还在未来(目标日在账户本地还没
      走完),钳到当前时刻,按"拉到现在为止"打标签。
    """
    if not is_review(china_date):
        return _floor_half_hour(account_local_dt(china_date, tz_name))
    target = datetime.strptime(date_prefix(china_date), "%Y-%m-%d").date()
    account_next_midnight = datetime(
        target.year, target.month, target.day,
        tzinfo=resolve_tz(tz_name),
    ) + timedelta(days=1)
    return min(account_next_midnight, _floor_half_hour(datetime.now(resolve_tz(tz_name))))


def account_local_dt(china_date: str, tz_name: str) -> datetime:
    """hourly 消息的中国半点时刻(兼容只到小时的调试消息)换算成账户本地时刻。"""
    fmt = MinuteFormat if ":" in china_date else HourFormat
    dt = datetime.strptime(china_date, fmt).replace(tzinfo=_SHANGHAI)
    return dt.astimezone(resolve_tz(tz_name))


def compute_fetch_day(china_date: str, tz_name: str) -> str:
    """该轮要拉的账户日(transform 与 account_consumer 共用同一实现):
    - hourly:账户本地日的首轮(本地 [00:00, 00:30) 档)收尾昨天,其余(含 00:30)拉当天
    - review:账户本地次日 0 点减一天回 target;目标日未走完被钳到当前时刻的取当天
    """
    if is_review(china_date):
        account_date = effective_account_dt(china_date, tz_name)
        if account_date.hour == 0:
            return (account_date - timedelta(days=1)).strftime("%Y-%m-%d")
        return account_date.strftime("%Y-%m-%d")
    local = account_local_dt(china_date, tz_name)
    if local.hour == 0 and local.minute < 30:
        return (local - timedelta(days=1)).strftime("%Y-%m-%d")
    return local.strftime("%Y-%m-%d")
