"""ad_sync_new 的 **dispatcher**:从 `ad_sync_new:dev_queue` 拉一个 dev message,
解析 dev → 列 account_ids → 抢账户锁 → 把账户级消息分发到 `account_queue:{dev_id}`,
真正的 fetch_all / transform / write_to_doris 交给 `account_consumer.py` 跑。

跟改造前(单进程内 ThreadPoolExecutor)的关键差异:
  - **本进程不再干活**,只做分发;账户级任务由 account_consumer 进程分布式消费
  - 每个 account_id 一把 redis 锁,**防止同一户被不同 dev 重复抓**(共享 BUC quota)
  - 每个 dev 一条独立 account_queue:{dev_id}。account_consumer 通过
    `SETNX dev_claim:{dev_id}` 抢锁实现 "1 进程 = 1 dev",进程内 ThreadPoolExecutor 并发

流程:
  1. blpop dev message {_id, date, type}(review 由 date 自动推断,见 consts.is_review)
  2. _load_dev(): mongo 查 dev (PRODUCER -> accounts;PERSONAL_PRODUCER -> personal+accounts)
  3. _create_or_resume_history(): 复用老 `ad_sync_history` 去重 + 状态机
  4. _list_account_ids() 从 mongo(personal_accounts / fb_system_users)缓存的 accounts 字段拿 account_id 列表
     —— 顺带对第一个 account 跑一次轻量 /insights 探测,把 ads_api_access_tier 缓存进 api 后塞进 base_message
  5. for each aid: SET NX account_lock → 抢到的进 acquired,抢不到的 skipped_locked
  6. 把 base_message 一次性写到 dev_payload:{history_id}
  7. RPUSH 每个 account msg(只带 history_id + account_id + dev_id)→ account_queue:{dev_id}

终态:DevWorker idle 退出时给当前持有的 history 写 COMPLETED + 删 dev_payload。
跨整点切到新 history 时直接覆盖,旧 history 留 STARTED(可接受)。
dispatcher 在 acquired=0 时直接写 COMPLETED。

外部 supervisor 起进程方式:
  python -m tasks.ad_sync_new.dispatcher
"""

import json
import logging
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from bson import ObjectId
from facebook_business.exceptions import FacebookRequestError
from tenacity import retry, retry_if_exception_type, stop_never, wait_fixed

from conf.api_conf import get_proxies
from conf.log_conf import init
from db.clients import mongo_client, redis_cli
from utils.common import RunStatus
from utils.common_util import get_error, handle_error
from utils.tg import send_tg_msg

from tasks.ad_sync_new.airbyte import API
from tasks.ad_sync_new.history import update_history_status
from tasks.ad_sync_new.consts import (
    ACCOUNT_LOCK_TTL_SEC,
    DEV_INFLIGHT_CAP,
    REDIS_ACCOUNT_LOCK_FMT,
    REDIS_ACCOUNT_QUEUE_FMT,
    REDIS_DEV_CLAIM_FMT,
    REDIS_DEV_LATEST_HISTORY_FMT,
    REDIS_DEV_PAYLOAD_FMT,
    REDIS_DEV_QUEUE,
    REVIEW_PAYLOAD_TTL_SEC,
    ProducerMethod,
    date_prefix,
    is_review,
)


logger = logging.getLogger(__name__)


# ── dev 信息加载 ─────────────────────────────────────────────────────────────

def _load_dev(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """根据 producer message 加载 dev 完整记录(对齐老 ad_sync.consumer_process)。"""
    _id = msg["_id"]
    _type = msg.get("type")

    if _type == ProducerMethod.PRODUCER.value:
        dev = mongo_client["accounts"].find_one({"_id": ObjectId(_id)})

    elif _type == ProducerMethod.PERSONAL_PRODUCER.value:
        dev = mongo_client["personal_accounts"].find_one(
            {"_id": _id},
            projection={
                "_id": 1, "access_token": 1, "app_id": 1, "name": 1,
                "create_at": 1, "status": 1, "user_name": 1,
            },
        )
        if not dev:
            logger.warning("[ad_sync_new] personal_accounts 找不到 _id=%s", _id)
            return None
        app_config = mongo_client["accounts"].find_one(
            {"app_id": dev.get("app_id"), "status": 1},
            projection={
                "_id": 0, "ad_platform": 1, "app_secret": 1, "dev_id": 1, "proxy": 1,
            },
        )
        if not app_config:
            logger.error(
                "[ad_sync_new] 未找到可用的开发者 app_id=%s,个号 id=%s name=%s",
                dev.get("app_id"), _id, dev.get("name"),
            )
            return None
        # 个号 token 拉的数据,placer_id 存个号 user_name(不污染 dev_id)
        dev["placer_id"] = dev.pop("user_name", None)
        # 把 dev_id 改成"企业 dev_id_个号 _id" —— 让 redis 维度(account_queue
        # 等)按个号独立分桶。如果 join 后字段同名,update 会把 personal 的
        # access_token 等保留下来,但 dev_id 字段需要我们手动重写,
        # 不能让 app_config 的 dev_id 直接覆盖。
        enterprise_dev_id = app_config.get("dev_id")
        dev.update(app_config)
        if enterprise_dev_id is not None:
            dev["dev_id"] = f"{enterprise_dev_id}_{dev['_id']}"
    else:
        logger.warning("[ad_sync_new] 未知 type: %s", _type)
        return None

    if not dev:
        logger.error("[ad_sync_new] dev _id=%s 不存在", _id)
        return None
    return dev


# ── 加载 dev + 组装 base_message + 建 API(共用 helper) ──────────────────────

def prepare_base_message(
    msg: Dict[str, Any], history_id: str,
) -> Optional[Tuple[Dict[str, Any], API, str]]:
    """加载 dev + 组装 base_message + 建 API 实例。给 dispatch_dev 和本地调试
    脚本共用,避免在 debug 脚本里手抄一遍组装逻辑。

    Args:
        msg: producer message {"_id", "date", "type"}(review 由 date 隐含)
        history_id: 用作 base_message["_id"] —— dispatch_dev 传真实 mongo history_id,
            debug 脚本可以传 str(ObjectId()) 当占位

    Returns:
        (base_message, api, dev_id) 或 None(dev 不存在 / 禁用 / 非 facebook 平台)
    """
    dev = _load_dev(msg)
    if not dev:
        return None
    if dev.get("status") not in (1, True):
        logger.warning("[ad_sync_new] dev 已禁用 _id=%s,跳过", msg.get("_id"))
        return None
    if dev.get("ad_platform", "facebook") != "facebook":
        logger.warning(
            "[ad_sync_new] ad_platform=%s 当前不支持,跳过 dev=%s",
            dev.get("ad_platform"), dev.get("dev_id"),
        )
        return None

    dev_mongo_id = str(dev.pop("_id"))
    dev_id = dev.get("dev_id")
    now_iso = datetime.now(timezone.utc).isoformat()
    base_message: Dict[str, Any] = {
        **dev,
        "_id": history_id,
        "dev_mongo_id": dev_mongo_id,
        "date": msg["date"],
        "create_time": now_iso,
        "update_time": now_iso,
    }
    api = API(
        app_id=base_message["app_id"],
        app_secret=base_message["app_secret"],
        access_token=base_message["access_token"],
        proxies=get_proxies(base_message.get("proxy")),
    )
    return base_message, api, dev_id


# ── ad_sync_history 状态机 (复用老表) ────────────────────────────────────────

def _create_or_resume_history(
    dev: Dict[str, Any], msg: Dict[str, Any], dev_mongo_id: str
) -> Optional[str]:
    """复刻老 ad_sync.consumer_process 的 ad_sync_history 去重 + 创建逻辑。
    返回 history _id;若有重复任务返回 None(consumer 应跳过)。
    """
    # ad_sync_history.date 跟 message["date"] 同步,到半点粒度(:00 / :30 是不同串)。
    # 于是去重像跨小时一样把半点当独立 run:上个半点没跑完也不挡下个半点开跑;
    # "一天同时只跑一个账户 + 下个半点只捡没跑完的"由 redis 账户锁(颗粒到天)兜底。
    one = mongo_client["ad_sync_history"].find_one(
        {"dev_mongo_id": dev_mongo_id, "date": msg["date"]},
        projection={"run_status": 1},
    )
    if one and one["run_status"] not in [
        RunStatus.COMPLETED.value,
        RunStatus.FAILED.value,
        RunStatus.SENDING.value,
    ]:
        logger.warning(
            "[ad_sync_new] dev_mongo_id=%s date=%s 有重复任务,跳过",
            dev_mongo_id, msg["date"],
        )
        return None

    now = datetime.now(timezone.utc)
    history_doc = {
        **dev,
        "dev_mongo_id": dev_mongo_id,
        "date": msg["date"],
        "run_status": RunStatus.SENDING.value,
        "create_time": now,
        "update_time": now,
    }
    history_doc.pop("_id", None)  # 不带原 dev._id

    result = mongo_client["ad_sync_history"].insert_one(history_doc)
    return str(result.inserted_id)


# ── account_id 列表 (DB) ────────────────────────────────────────────────────

def _list_account_ids(msg: Dict[str, Any], base_message: Dict[str, Any]) -> List[str]:
    """读 mongo 缓存的 `accounts` 字段,返回带 "act_" 前缀的 account_id 列表。

    - PERSONAL_PRODUCER → `personal_accounts.accounts`(以 msg["_id"] 为主键)
    - PRODUCER          → `fb_system_users.accounts`(以 dev.app_id 为主键)

    accounts 字段由 fb_business_sync 维护,形状 `[{"id": "<numeric>", "name": "..."}]`。
    返回前统一补 "act_" 前缀,跟旧 me.get_ad_accounts() 的输出对齐(REDIS 锁键 / worker
    侧 _strip_act_prefix 都依赖这个前缀)。
    """
    msg_type = msg.get("type")
    if msg_type == ProducerMethod.PERSONAL_PRODUCER.value:
        doc = mongo_client["personal_accounts"].find_one(
            {"_id": msg["_id"]}, projection={"accounts": 1},
        )
    elif msg_type == ProducerMethod.PRODUCER.value:
        app_id = base_message.get("app_id")
        doc = mongo_client["fb_system_users"].find_one(
            {"_id": app_id}, projection={"accounts": 1},
        )
        if not doc:
            logger.warning(
                "[_list_account_ids] fb_system_users 找不到 app_id=%s", app_id,
            )
    else:
        logger.warning("[_list_account_ids] 未知 msg.type=%s", msg_type)
        return []

    accounts = (doc or {}).get("accounts") or []
    result: List[str] = []
    for a in accounts:
        aid = a.get("id")
        if not aid:
            continue
        result.append(aid if aid.startswith("act_") else f"act_{aid}")
    logger.warning(
        "[_list_account_ids] type=%s 共 %d 个 account (from mongo)",
        msg_type, len(result),
    )
    return result


def _personal_defer_accounts(self_id: Any, account_ids: List[str]) -> set:
    """personal dev 让位:同一账户被多个 personal dev 共享时,只让"账户总数最少"的
    dev 抢锁处理,其余让出(不抢锁)。返回应让出的 account_id 集合(act_ 前缀,跟
    account_ids 同形)。存在另一 personal dev 账户数严格更少且也有此账户 → 让出;
    打平不让(回退 SETNX 抢锁)。查询失败 → 不让位(宁可竞态,不可漏户)。
    account_id 在 mongo / lock 两种前缀形态都可能存在,统一去 act_ 前缀比对。
    只跟 status=True(对齐 producer 入队条件)的 dev 比 —— 否则让位给禁用/不跑的
    更小 dev,这账户没人捡会漏。"""
    def _num(a: str) -> str:
        return a[4:] if a.startswith("act_") else a

    num_to_orig = {_num(a): a for a in account_ids}
    nums = set(num_to_orig)
    if not nums:
        return set()
    current_count = len(nums)
    in_vals = list(nums) + [f"act_{n}" for n in nums]
    try:
        docs = mongo_client["personal_accounts"].find(
            {"_id": {"$ne": self_id}, "status": True, "accounts.id": {"$in": in_vals}},
            projection={"accounts.id": 1},
        )
        defer: set = set()
        for d in docs:
            other = {_num(str(a["id"])) for a in (d.get("accounts") or []) if a.get("id") is not None}
            if len(other) < current_count:
                for n in nums & other:
                    defer.add(num_to_orig[n])
        return defer
    except Exception as e:
        logger.warning("[ad_sync_new] personal 让位查询失败,本轮不让位: %s", e)
        return set()


class DevTokenInvalidError(Exception):
    """探测时命中 FB code=190(token 失效 / session 失效)。token 是 dev 级凭据,
    任一账户上撞到都意味着整 dev 这一轮都跑不动 —— 由 dispatch_dev 接住后跳过整个 dev
    + 发 TG 告警,而不是继续重试或往 account_queue 发任务。

    参照 `fb_business_consumer._should_deactivate_on_user_error`:code=190 即 token 失效大类,
    无论 subcode 均判失效。
    """

    def __init__(self, account_id: str, fb_exc: FacebookRequestError):
        self.account_id = account_id
        self.fb_exc = fb_exc
        super().__init__(f"account={account_id} OAuth 190: {fb_exc.api_error_message()}")


class DevProxyUnreachableError(Exception):
    """探测时撞到连接层错误(代理 → graph.facebook.com 连不上,且底层 call 已
    backoff 重试 5 次仍失败)。代理是 dev 级配置,任一户连不上即整 dev 这一轮跑不动 ——
    跟 DevTokenInvalidError 同机制:dispatch_dev 接住后跳过整个 dev + 发 TG,不派发任务。
    数据缺口交给 review(D+1 自动全量重抓)补,不在本轮逐户重试 / 逐户告警。
    """

    def __init__(self, account_id: str, exc: Exception):
        self.account_id = account_id
        self.exc = exc
        super().__init__(f"account={account_id} proxy unreachable: {exc}")


def _fb_error_code(exc: FacebookRequestError) -> Optional[int]:
    """从 FacebookRequestError 抽 error.code,兼容 api_error_code() / body.error.code 两种来源。"""
    code = None
    try:
        if callable(getattr(exc, "api_error_code", None)):
            code = exc.api_error_code()
    except Exception:
        pass
    try:
        body = exc.body() if callable(getattr(exc, "body", None)) else None
        if isinstance(body, dict):
            code = body.get("error", {}).get("code", code)
    except Exception:
        pass
    return code


def _probe_ads_api_access_tier(api: API, account_ids: List[str]) -> None:
    """对第一个可用 account 跑一次轻量 /insights 请求(empty insights call),
    让响应 header 把 `ads_api_access_tier` 缓存进 `api.api._ads_api_access_tier`。

    跟 `async_job_manager.APILimit.refresh_throttle` 同思路 —— 一次廉价 ping 顺带把
    tier / throttle header 都拉回来。

    异常处理:
      - 撞到 FB code=190(OAuthException,token / session 失效)→ 抛 DevTokenInvalidError,
        让 dispatch_dev 整 dev 跳过 + TG 告警,不要继续探下一个 account,也不要派发任务。
      - 其它账户级错误(账户禁用 / 权限缺失等)→ 轮下一个 account 继续探测。
      - 全失败时 tier 留空,下游 pipeline 按非 standard_access 处理(`pipeline.py:284`)。
    """
    for aid in account_ids:
        try:
            api.get_account(account_id=aid).get_insights()
            return
        except FacebookRequestError as e:
            if _fb_error_code(e) == 190:
                raise DevTokenInvalidError(aid, e) from e
            logger.warning(
                "[_probe_ads_api_access_tier] account=%s 探测失败,尝试下一个: %s",
                aid, e,
            )
        except requests.exceptions.ConnectionError as e:
            # 连接层失败(ConnectTimeout 等,已被底层 backoff 重试 5 次)→ 代理通道问题,
            # dev 级,整 dev 跳过本轮。ReadTimeout 不归此列(不走 backoff、多是单请求慢),
            # 落到下面 except 试下一户,不拿它整 dev 跳过。
            raise DevProxyUnreachableError(aid, e) from e
        except Exception as e:
            logger.warning(
                "[_probe_ads_api_access_tier] account=%s 探测失败,尝试下一个: %s",
                aid, e,
            )
    logger.warning("[_probe_ads_api_access_tier] 全部 account 探测失败,tier 留空")


# ── dispatcher 主流程 ───────────────────────────────────────────────────────

@handle_error("ad_sync_new dev 分发报错")
def dispatch_dev(msg: Dict[str, Any]) -> None:
    """处理一个 dev message:加载 dev → 列 account_ids → 抢账户锁 → 写 dev_payload /
    分发账户级消息到子队列。**本进程不跑账户业务**,交给 worker。
    """
    # 先单独加载 dev 拿 dev_mongo_id(用于 _create_or_resume_history 去重)
    dev_peek = _load_dev(msg)
    if not dev_peek:
        return
    if dev_peek.get("status") not in (1, True):
        logger.warning("[ad_sync_new] dev 已禁用 _id=%s,跳过", msg.get("_id"))
        return
    dev_mongo_id = str(dev_peek["_id"])
    logger.info(
        "[ad_sync_new] 开始分发 dev_id=%s app_id=%s mongo_id=%s type=%s",
        dev_peek.get("dev_id"), dev_peek.get("app_id"), dev_mongo_id, msg.get("type"),
    )

    history_id = _create_or_resume_history(dev_peek, msg, dev_mongo_id)
    if not history_id:
        return  # 重复任务,跳过

    acquired: List[str] = []  # 用于异常分支回滚账户锁
    date_token = date_prefix(msg["date"])  # redis key 里用日期段(无 HH),颗粒到 "天"
    # except 里要用 dev_id 打日志 / 发 TG —— 在 try 之前用 dev_peek 兜底初始化,
    # 防止异常出在 prepare_base_message 之前(此时 prepared 解包还没发生)时再炸 NameError。
    dev_id = dev_peek.get("dev_id")

    try:
        update_history_status(history_id, RunStatus.STARTED)

        prepared = prepare_base_message(msg, history_id=history_id)
        if prepared is None:
            update_history_status(history_id, RunStatus.FAILED, error="prepare_base_message failed")
            return
        base_message, api, dev_id = prepared

        account_ids = _list_account_ids(msg, base_message)
        total_accounts = len(account_ids)
        # 之前 _list_account_ids 走 me.get_ad_accounts() 顺带刷出 tier;现在 account_ids
        # 来自 mongo 缓存,没碰 FB API,得单独探一次让 base_message 拿到 tier 透传给 worker。
        _probe_ads_api_access_tier(api, account_ids)
        base_message["ads_api_access_tier"] = api.api.ads_api_access_tier
        logger.warning(
            "[ad_sync_new][%s] mongo accounts -> %d 个 account, tier=%s",
            dev_id, total_accounts, base_message["ads_api_access_tier"],
        )

        # ── Step 1: 抢账户锁 ────────────────────────────────────────────────
        # 同一个 FB account_id 可能挂在多个 dev 下;某个 dev 跑的时候独占,
        # 其它 dev 看到锁就跳过(这一轮不发任务,等下个 hour 再说)。
        # 用 pipeline 一次性把 N 个 SET NX 发出去,避免 N 次串行往返(本地调试
        # 连远程 redis 时 1000+ 次 RTT 会卡好几分钟)。transaction=False:
        # 只做 pipeline 批量,不开 MULTI/EXEC,每个 SET NX 仍各自独立返回。
        # personal dev 让位:同一账户被多个 personal dev 共享时,只让账户总数最少的
        # 那个去抢锁,其余 dev 不抢(各 dev 用同一份 mongo 数据独立预判,结论一致,
        # 不会重复)。enterprise/PRODUCER 不受影响。
        defer: set = set()
        if msg.get("type") == ProducerMethod.PERSONAL_PRODUCER.value:
            defer = _personal_defer_accounts(msg["_id"], account_ids)
        lock_targets = [aid for aid in account_ids if aid not in defer]

        skipped_locked: List[str] = []
        pipe = redis_cli.pipeline(transaction=False)
        for aid in lock_targets:
            pipe.set(
                REDIS_ACCOUNT_LOCK_FMT.format(account_id=aid, date=date_token),
                history_id, nx=True, ex=ACCOUNT_LOCK_TTL_SEC,
            )
        for aid, ok in zip(lock_targets, pipe.execute()):
            if ok:
                acquired.append(aid)
            else:
                skipped_locked.append(aid)

        pushed_count = len(acquired)
        logger.warning(
            "[ad_sync_new][%s] account 分发统计: total=%d 抢锁成功=%d 被其它 dev 锁=%d personal让位=%d",
            dev_id, total_accounts, pushed_count, len(skipped_locked), len(defer),
        )

        # ── Step 2: 没有可派发的账户 → 立刻写 COMPLETED 收工 ─────────────────
        if pushed_count == 0:
            note = (
                f"all {total_accounts} accounts locked by other devs"
                if total_accounts else "no accounts under this dev"
            )
            update_history_status(
                history_id, RunStatus.COMPLETED,
                additional_fields={"note": note},
            )
            return

        # ── Step 3: dev_payload 写一次,worker 端按 history_id 拉 ────────────
        # TTL 统一到下下个中国整点 -60s:让慢账户在跨过下个整点后仍能拉到 payload,
        # 同时确保再下一次 cron 触发前 payload 必然消失,避免 worker 用错凭据。
        # -60s 余量避开 dispatcher 跟 cron 之间的时钟漂移 / 调度抖动。
        if is_review(msg["date"]):
            payload_ttl_sec = REVIEW_PAYLOAD_TTL_SEC
        else:
            china_tz = timezone(timedelta(hours=8))
            now_cn = datetime.now(china_tz)
            next_next_hour_cn = (now_cn + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
            payload_ttl_sec = max(int((next_next_hour_cn - now_cn).total_seconds()) - 60, 1)

        payload_key = REDIS_DEV_PAYLOAD_FMT.format(history_id=history_id)
        # base_message 里可能含 datetime(MongoDB ObjectId 已经在上面 pop / str 化了);
        # default=str 兜底任何不可序列化的对象。
        redis_cli.set(
            payload_key,
            json.dumps(base_message, default=str),
            ex=payload_ttl_sec,
        )

        # ── Step 4: 推 account msg ──────────────────────────────────────────
        # 单条 RPUSH 带多个 value 比 N 条 RPUSH 在网络/CPU 上都更省。
        # worker 端通过 SCAN match=account_queue:* 发现非空 queue,不再需要 active_devs。
        queue_key = REDIS_ACCOUNT_QUEUE_FMT.format(dev_id=dev_id, date=date_token)
        msg_payloads = [
            json.dumps({
                "account_id": aid,
                "history_id": history_id,
                "dev_id": dev_id,
            })
            for aid in acquired
        ]
        redis_cli.rpush(queue_key, *msg_payloads)

        # 更新"最新 history"指针:worker 据此把进度切到本 history,旧的停更写 ABORT。
        redis_cli.set(
            REDIS_DEV_LATEST_HISTORY_FMT.format(dev_id=dev_id, date=date_token),
            history_id, ex=payload_ttl_sec,
        )

        logger.warning(
            "[ad_sync_new][%s] 分发完成 history_id=%s 推送 %d 个 account → %s",
            dev_id, history_id, pushed_count, queue_key,
        )

    except DevTokenInvalidError as e:
        # token 失效是终态错误 —— 不重试、不派发任务,只发 TG 提醒人工换 token。
        # 走在 _probe_ads_api_access_tier 阶段抛出,此时 acquired 还是空 / 没写 dev_payload,
        # 不需要回滚 redis。
        fb_msg = e.fb_exc.api_error_message() if e.fb_exc else str(e)
        logger.warning(
            "[ad_sync_new][%s] dev token 失效(OAuth 190),跳过该 dev: account=%s err=%s",
            dev_id, e.account_id, fb_msg,
        )
        send_tg_msg(
            f"{dev_peek.get('agent_lines')}\n{dev_peek.get('placer_id')}\n{dev_id}\n"
            f"dev token 失效,跳过本轮分发(ad_sync_new): OAuth 190 {fb_msg}"
        )
        update_history_status(
            history_id, RunStatus.FAILED,
            error=f"OAuth 190 token invalid on account={e.account_id}: {fb_msg}",
        )
        # 释放已抢到的账户锁(防御性 —— 这一分支理论上 acquired 为空)
        for aid in acquired:
            try:
                redis_cli.delete(
                    REDIS_ACCOUNT_LOCK_FMT.format(account_id=aid, date=date_token)
                )
            except Exception:
                pass
        return

    except DevProxyUnreachableError as e:
        # 代理 → graph.facebook.com 连不上(已 backoff 5 次)。跟 token 失效同机制:
        # 不重试、不派发,发一条 TG;数据缺口交给 review(D+1 自动重抓)补。
        # 走在 probe 阶段抛出,此时 acquired 为空 / 没写 payload,释放锁是防御性的。
        logger.warning(
            "[ad_sync_new][%s] 代理连不上,跳过该 dev: account=%s err=%s",
            dev_id, e.account_id, e.exc,
        )
        send_tg_msg(
            f"{dev_peek.get('agent_lines')}\n{dev_peek.get('placer_id')}\n{dev_id}\n"
            f"代理连不上,跳过本轮分发(ad_sync_new),数据等 review 补: {e.exc}"
        )
        update_history_status(
            history_id, RunStatus.FAILED,
            error=f"proxy unreachable on account={e.account_id}: {e.exc}",
        )
        for aid in acquired:
            try:
                redis_cli.delete(
                    REDIS_ACCOUNT_LOCK_FMT.format(account_id=aid, date=date_token)
                )
            except Exception:
                pass
        return

    except Exception as e:
        error_str = "\n".join(get_error())
        logger.error(
            "[ad_sync_new][%s] dispatch 失败: %s\n%s",
            dev_id, e, error_str,
        )
        send_tg_msg(
            f"{dev_peek.get('agent_lines')}\n{dev_peek.get('placer_id')}\n{dev_id}\n"
            f"账户分发失败(ad_sync_new dispatch): {e}"
        )
        update_history_status(history_id, RunStatus.FAILED, error=error_str)
        # 释放已抢到但还没推消息的账户锁,避免堵下一轮
        for aid in acquired:
            try:
                redis_cli.delete(
                    REDIS_ACCOUNT_LOCK_FMT.format(account_id=aid, date=date_token)
                )
            except Exception:
                pass
        raise


# ── 本地调试入口(不走 redis dev_queue,但仍走 account_queue) ────────────────

def dispatch_dev_locally(
    dev_mongo_id: str,
    date: Optional[str] = None,
    is_personal: bool = False,
) -> None:
    """本地直接跑一个 dev 的分发流程,**绕过 dev_queue 但仍写 account_queue**。

    跑完后需要有 account_consumer 在线消费 account_queue 才能看到 doris 落盘。
    review 由 date 自动判定:传 ``"YYYY-MM-DD"``(过去那天)= review;不传 = 当前整点。
    """
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
    logger.warning("[ad_sync_new] 本地调试 dispatcher:msg=%s", msg)
    dispatch_dev(msg)


def run_dev_locally(
    dev_mongo_id: str,
    date: Optional[str] = None,
    is_personal: bool = False,
) -> None:
    """**端到端本地调试**:走完整 prod 链路 —— dispatcher 推消息到 account_queue,
    然后同进程实例化 DevWorker 直接消费(SETNX claim、ThreadPoolExecutor、
    progress 写 mongo 全跟生产一致)。一条命令完成 fetch_all + transform +
    write_to_doris + ad_sync_history 终态写入。

    注意:**会跟生产 account_consumer 抢同一个 dev_claim**。本地跑前先确保
    生产没在跑同一个 dev_id(或者直接用一个只本地有数据的测试 dev)。
    review 由 date 自动判定。
    """
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

    # 先 peek 一次 dev 拿 dev_id(用于本地启 DevWorker)
    peek = _load_dev(msg)
    if not peek:
        logger.error("[ad_sync_new] 本地调试找不到 dev _id=%s", dev_mongo_id)
        return
    dev_id = peek.get("dev_id")
    if not dev_id:
        logger.error("[ad_sync_new] 本地调试 dev 没有 dev_id 字段 _id=%s", dev_mongo_id)
        return

    logger.warning(
        "[ad_sync_new] 本地端到端调试:dispatch_dev + DevWorker.run() dev_id=%s",
        dev_id,
    )
    dispatch_dev(msg)

    # DevWorker.run() 内部 SETNX claim 自己抢锁,跑完(queue 空 + running 空)自动退出
    from concurrent.futures import ThreadPoolExecutor

    from tasks.ad_sync_new.account_consumer import DevWorker
    # 直接强 claim(避免被生产 worker 抢):用 set ex=...,not nx;就跟 worker 自己续期一样
    day = date_prefix(msg["date"])
    redis_cli.set(
        REDIS_DEV_CLAIM_FMT.format(dev_id=dev_id, date=day), "1", ex=70,
    )
    worker = DevWorker(dev_id, msg["date"])
    executor = ThreadPoolExecutor(max_workers=DEV_INFLIGHT_CAP, thread_name_prefix="acct")
    try:
        worker.run(executor)
    finally:
        executor.shutdown(wait=True)
    logger.warning("[ad_sync_new] 本地端到端调试完成 dev_id=%s", dev_id)


def _log_retry(retry_state):
    exception = retry_state.outcome.exception()
    err = "".join(
        traceback.format_exception(type(exception), exception, exception.__traceback__)
    )
    logger.error(
        "[ad_sync_new] dispatcher 第 %d 次失败,%ds 后重试: %s",
        retry_state.attempt_number, retry_state.idle_for, err,
    )


@retry(
    stop=stop_never,
    wait=wait_fixed(5),
    retry=retry_if_exception_type(Exception),
    before_sleep=_log_retry,
    reraise=True,
)
def consumer_run():
    """主入口 —— blpop dev_queue,顺序分发。"""
    logger.warning(
        "[ad_sync_new] dispatcher 已启动 queue=%s,等待 dev message...",
        REDIS_DEV_QUEUE,
    )
    while True:
        result = redis_cli.blpop(REDIS_DEV_QUEUE, timeout=30)
        if result:
            _, message_str = result
            msg = json.loads(message_str)
            dispatch_dev(msg)


if __name__ == "__main__":
    init("ad_sync_new_consumer")
    consumer_run()
