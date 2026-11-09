"""ad_sync_new account-level worker。1 进程 = 1 dev_id。

跑完一个 dev 直接 os._exit(0),靠 docker restart 重置 RSS
(executor 重建救不回,glibc / SDK 模块级 pin)。

启动: python -m tasks.ad_sync_new.account_consumer
"""

import ctypes
import json
import logging
import os
import random
import threading
import time
import traceback
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from facebook_business.exceptions import FacebookRequestError
from tenacity import retry, retry_if_exception_type, stop_never, wait_fixed

from conf.api_conf import get_proxies
from conf.log_conf import init
from db.clients import redis_cli
from utils.common import RunStatus
from utils.common_util import get_error
from utils.tg import send_tg_msg

from tasks.ad_sync_new import pipeline, transform
from tasks.ad_sync_new.airbyte import API
from tasks.ad_sync_new.consts import (
    ACCOUNT_LOCK_TTL_SEC,
    DEV_CLAIM_TTL_SEC,
    DEV_INFLIGHT_CAP,
    DEV_THREADS_MIN,
    DEV_THREADS_PER_ACCOUNTS,
    REDIS_ACCOUNT_LOCK_FMT,
    REDIS_ACCOUNT_QUEUE_FMT,
    REDIS_DEV_CLAIM_FMT,
    REDIS_DEV_LATEST_HISTORY_FMT,
    REDIS_DEV_PAYLOAD_FMT,
    REDIS_REVIEW_DEV_LOCK_FMT,
    compute_fetch_day,
    date_prefix,
    is_review,
)
from tasks.ad_sync_new.history import update_history_status
from tasks.ad_sync_new.doris_writer import enqueue_to_doris, flush_doris


logger = logging.getLogger(__name__)

# account 子线程内所有日志(含 pipeline / transform)自动带 account_id 字段(OTel 导出)
_account_id_ctx: ContextVar[Optional[str]] = ContextVar("account_id", default=None)

_old_record_factory = logging.getLogRecordFactory()


def _record_factory(*args, **kwargs):
    record = _old_record_factory(*args, **kwargs)
    account_id = _account_id_ctx.get()
    if account_id:
        record.account_id = account_id
    return record


logging.setLogRecordFactory(_record_factory)


IDLE_SLEEP_SEC = 5
ERROR_BACKOFF_SEC = 2.0
# wait timeout 同时也是 EXPIRE claim TTL 的最大延迟,须远小于 DEV_CLAIM_TTL_SEC
IDLE_CHECK_INTERVAL_SEC = 5
# 账户级 kill 阈值:hourly/半点 暂调 3h 观察 batch 化后真实耗时(确认后调回);
# review 40min。跨半点不会重派同户 —— 主循环对在跑的 account 锁续期(见 run)。
ACCOUNT_KILL_HOURLY_SEC = 3 * 60 * 60
ACCOUNT_KILL_REVIEW_SEC = 40 * 60
# 跑超过该时长的账户视为慢户,每个慢户给 inflight 配额 +1,补偿被占住的线程
SLOW_ACCOUNT_BOOST_THRESHOLD_SEC = 10 * 60

REDIS_AD_SYNC_DONE_KEY_FMT = "ad_sync_done:fb:{china_date}:{campaign_id}"
AD_SYNC_DONE_TTL_SEC = 3600


def _publish_campaigns_with_agent_line(rows: list) -> int:
    """筛"任意层级匹配到代理线"的系列,SET 到 redis,TTL=1h。
    campaign 行的 agent_line 只来自 campaign_name 匹配,ad 行落地页匹配出的
    不会回写到 campaign 行;遍历到 ad 行时回填同 cid 的 campaign。
    """
    campaigns: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        cid = row.get("campaign_id")
        if not cid:
            continue
        level = row.get("level")
        if level == "campaign":
            campaigns[cid] = dict(row)
        elif level == "ad" and row.get("agent_line"):
            camp = campaigns.get(cid)
            if camp is not None and not camp.get("agent_line"):
                camp["agent_line"] = row.get("agent_line")
                camp["placer_id"] = row.get("placer_id")
                camp["department"] = row.get("department")
                camp["game_platform"] = row.get("game_platform")

    count = 0
    for cid, camp in campaigns.items():
        if not camp.get("agent_line"):
            continue
        china_date = camp.get("china_date")
        if not china_date:
            continue
        # 行内时间已到半点分钟;对外 redis key/value 维持小时粒度旧格式
        key = REDIS_AD_SYNC_DONE_KEY_FMT.format(
            china_date=china_date.split(":")[0], campaign_id=cid,
        )
        value = json.dumps({
            "campaign_id": cid,
            "campaign_name": camp.get("campaign_name"),
            "account_id": camp.get("account_id"),
            "account_name": camp.get("account_name"),
            "agent_line": camp.get("agent_line"),
            "department": camp.get("department"),
            "placer_id": camp.get("placer_id"),
            "game_platform": camp.get("game_platform"),
            "objective": camp.get("objective"),
            "ad_platform": camp.get("ad_platform"),
            "dev_id": camp.get("dev_id"),
            "timezone_name": camp.get("timezone_name"),
            "date": (camp.get("date") or "").split(":")[0] or None,
        }, ensure_ascii=False)
        try:
            redis_cli.set(key, value, ex=AD_SYNC_DONE_TTL_SEC)
            count += 1
        except Exception as e:
            logger.error(
                "[ad_sync_new] 推送 ad_sync_done 失败 campaign_id=%s err=%s",
                cid, e,
            )
    return count


class AccountTimeoutKill(Exception):
    """elapsed > 账户级 kill 阈值(见 DevWorker._account_kill_threshold_sec)由 _write_progress 异步注入到子线程,触发账户级失败收尾。"""


# ── 账户业务核心(纯函数,可重入,DevWorker 的 thread 跟 dispatcher.run_dev_locally 都调) ──

def _is_account_permission_error(exc: Exception) -> bool:
    """账号未授予 ads_management/ads_read 权限(FB #200),属单账号授权问题,只记日志不告警。"""
    return isinstance(exc, FacebookRequestError) and exc.api_error_code() == 200


def _process_one_account(
    account_id: str,
    base_message: Dict[str, Any],
    api: API,
) -> Dict[str, Any]:
    """一个 account 的完整业务流程。线程安全 —— api 是同 dev 共享单例,
    transform 纯函数,write_to_doris 走 mysql_client 连接池。
    """
    start_ts = datetime.now(timezone.utc)
    logger.info("[ad_sync_new] start account=%s", account_id)
    try:
        acct = api.get_account(account_id=account_id)
        if acct.get("account_status") == 101:
            logger.info("[ad_sync_new] account=%s 已 CLOSED(101),跳过拉取", account_id)
            return {
                "account_id": account_id, "ok": True, "rows": 0,
                "elapsed_sec": 0, "error": None,
            }
        tz_name = acct.get("timezone_name")
        if not tz_name:
            return {
                "account_id": account_id, "ok": False, "rows": 0,
                "elapsed_sec": 0, "error": "no timezone_name",
            }
        fetch_day = compute_fetch_day(base_message["date"], tz_name)
        account_message = {**base_message, "account_id": account_id}
        logger.info("[ad_sync_new] account=%s 步骤1 拉取 FB 数据 fetch_day=%s", account_id, fetch_day)
        _t_fetch = time.monotonic()
        bundle = pipeline.fetch_all(message=account_message, fetch_day=fetch_day)
        _t_transform = time.monotonic()
        # 每步耗时随完成即打,账户被 40min kill 时也能看到已完成步骤的耗时 + 卡在哪步
        logger.info(
            "[ad_sync_new] account=%s 步骤2 拉取完成 %.1fs,开始转换",
            account_id, _t_transform - _t_fetch,
        )
        rows = transform.bundle_to_doris_rows(account_message, bundle)
        _t_doris = time.monotonic()
        logger.info(
            "[ad_sync_new] account=%s 步骤3 转换完成 %.1fs %d 行,写入 doris",
            account_id, _t_doris - _t_transform, len(rows),
        )
        if rows:
            enqueue_to_doris(rows)
            published = _publish_campaigns_with_agent_line(rows)
            logger.info(
                "[ad_sync_new] account=%s 步骤4 入队+推送完成 %.1fs (%d 个系列)",
                account_id, time.monotonic() - _t_doris, published,
            )
        elapsed = (datetime.now(timezone.utc) - start_ts).total_seconds()
        return {
            "account_id": account_id, "ok": True, "rows": len(rows),
            "elapsed_sec": elapsed, "error": None,
        }
    except Exception as e:
        elapsed = (datetime.now(timezone.utc) - start_ts).total_seconds()
        return {
            "account_id": account_id, "ok": False, "rows": 0,
            "elapsed_sec": elapsed,
            "error": "\n".join(traceback.format_exception(type(e), e, e.__traceback__)),
            "alert": not _is_account_permission_error(e),
        }


# ── DevWorker:一个进程内一个实例,绑定一个 dev_id ──

class DevWorker:
    """绑定 (dev_id, date) 的工作单元。consumer_run 抢到 claim 后实例化并 run()。"""

    def __init__(self, dev_id: str, date: str):
        self.dev_id = dev_id
        # date 入参可带 HH,统一切到日期段做 redis key 颗粒度
        self.date = date_prefix(date)
        self.claim_key = REDIS_DEV_CLAIM_FMT.format(dev_id=dev_id, date=self.date)
        # review 日期额外持 per-dev 串行锁,跟 claim 同寿命;hourly(今天)为 None
        self.review_lock_key = (
            REDIS_REVIEW_DEV_LOCK_FMT.format(dev_id=dev_id)
            if is_review(self.date) else None
        )
        self.queue_key = REDIS_ACCOUNT_QUEUE_FMT.format(dev_id=dev_id, date=self.date)
        self.latest_history_key = REDIS_DEV_LATEST_HISTORY_FMT.format(dev_id=dev_id, date=self.date)
        # _history_id: 当前处理消息所属 history(管凭据 / 拉哪天)。
        # _report_history_id: 进度上报目标 history,跨整点切到最新(见 _advance_report_history),
        #   旧的写 ABORT 后不再更新 —— 跟处理 history 解耦,避免积压消息把旧 history 刷成 STARTED。
        self._history_id: Optional[str] = None
        self._report_history_id: Optional[str] = None
        self._base_message: Optional[Dict[str, Any]] = None
        self._api: Optional[API] = None
        self._state_lock = threading.Lock()
        self._processed_ok = 0
        self._processed_fail = 0
        self._progress_lock = threading.Lock()
        # account_id -> (monotonic 起跑时刻, 子线程 tid),tid 给超时杀线程用
        self._inflight_starts: Dict[str, Tuple[float, int]] = {}
        self._inflight_lock = threading.Lock()

    def _load_history_state(self, history_id: str) -> Optional[Tuple[Dict[str, Any], API]]:
        """拿 (base_message, api)。遇到不同 history_id 时覆盖切换;redis 没拿到 payload → None。"""
        with self._state_lock:
            if self._history_id != history_id:
                payload_key = REDIS_DEV_PAYLOAD_FMT.format(history_id=history_id)
                raw = redis_cli.get(payload_key)
                if not raw:
                    return None
                if self._history_id is not None:
                    logger.warning(
                        "[%s] 切换处理 history_id: old=%s new=%s",
                        self.dev_id, self._history_id, history_id,
                    )
                self._history_id = history_id
                self._base_message = json.loads(raw)
                self._api = API(
                    app_id=self._base_message["app_id"],
                    app_secret=self._base_message["app_secret"],
                    access_token=self._base_message["access_token"],
                    proxies=get_proxies(self._base_message.get("proxy")),
                )
            return self._base_message, self._api

    def _process_msg(self, msg: Dict[str, Any]) -> None:
        """子线程入口:_load_history_state → _process_one_account → finally 删 account_lock。"""
        history_id = msg["history_id"]
        account_id = msg["account_id"]
        ctx_token = _account_id_ctx.set(account_id)
        lock_key = REDIS_ACCOUNT_LOCK_FMT.format(
            account_id=account_id, date=self.date,
        )
        logger.info(
            "[%s] 子线程启动 account=%s history_id=%s",
            self.dev_id, account_id, history_id,
        )
        with self._inflight_lock:
            self._inflight_starts[account_id] = (time.monotonic(), threading.get_ident())

        try:
            state = self._load_history_state(history_id)
            if state is None:
                logger.error(
                    "[%s] dev_payload 不存在 history_id=%s,账户=%s 计为失败 (TTL 过期或 dispatcher 未写入)",
                    self.dev_id, history_id, account_id,
                )
                result = {
                    "account_id": account_id, "ok": False, "rows": 0,
                    "elapsed_sec": 0,
                    "error": "dev_payload missing or expired (dispatcher 可能挂了或 TTL 过期)",
                }
            else:
                base_message, api = state
                result = _process_one_account(account_id, base_message, api)

            with self._progress_lock:
                if result.get("ok"):
                    self._processed_ok += 1
                else:
                    self._processed_fail += 1

            if result.get("ok"):
                logger.info(
                    "[%s] account=%s 成功 rows=%d elapsed=%.1fs",
                    self.dev_id, account_id, result.get("rows", 0),
                    result.get("elapsed_sec", 0),
                )
            else:
                err_full = result.get("error") or ""
                err_tg = err_full[-500:].replace("\n", " ").strip()
                logger.error(
                    "[%s] account=%s 失败 elapsed=%.1fs err=\n%s",
                    self.dev_id, account_id, result.get("elapsed_sec", 0), err_full,
                )
                if result.get("alert", True):
                    send_tg_msg(
                        f"{self.dev_id} {account_id} 账户同步失败(ad_sync_new): {err_tg}"
                    )

        finally:
            try:
                redis_cli.delete(lock_key)
            except Exception as e:
                logger.error(
                    "[%s] 释放 account_lock 失败 account=%s err=%s",
                    self.dev_id, account_id, e,
                )
            with self._inflight_lock:
                self._inflight_starts.pop(account_id, None)
            logger.info("[%s] 子线程结束 account=%s", self.dev_id, account_id)
            _account_id_ctx.reset(ctx_token)

    def run(self, executor: ThreadPoolExecutor, max_inflight: int = DEV_INFLIGHT_CAP) -> None:
        """主循环:流式 LPOP + submit,wait FIRST_COMPLETED,维持 ≤ max_inflight
        (+ 慢户 boost)个 task 在跑。每轮顺手 EXPIRE claim,代替独立 heartbeat。
        queue 空 + running 空 → 退出。executor 是 consumer_run 注入的进程级单例,
        **不在这里 shutdown**。
        """
        logger.warning(
            "[%s] DevWorker 启动 max_inflight=%d", self.dev_id, max_inflight,
        )

        running: set = set()
        last_progress_ts = 0.0
        drained_cleanly = False

        try:
            while True:
                try:
                    redis_cli.expire(self.claim_key, DEV_CLAIM_TTL_SEC)
                    if self.review_lock_key:
                        redis_cli.expire(self.review_lock_key, DEV_CLAIM_TTL_SEC)
                except Exception as e:
                    logger.error("[%s] EXPIRE claim 失败: %s", self.dev_id, e)

                # 给在跑的 account 锁续期,使锁活到户实际跑完(kill 阈值可超 TTL/半点
                # 而不会被下轮重派);跑完 _process_msg finally 删锁。
                with self._inflight_lock:
                    inflight_ids = list(self._inflight_starts.keys())
                for aid in inflight_ids:
                    try:
                        redis_cli.expire(
                            REDIS_ACCOUNT_LOCK_FMT.format(account_id=aid, date=self.date),
                            ACCOUNT_LOCK_TTL_SEC,
                        )
                    except Exception:
                        pass

                # 每个 >10min 的慢户给配额 +1,补偿被它占住的线程
                with self._inflight_lock:
                    now_mono = time.monotonic()
                    slow_count = sum(
                        1 for ts, _ in self._inflight_starts.values()
                        if now_mono - ts > SLOW_ACCOUNT_BOOST_THRESHOLD_SEC
                    )
                cap = min(max_inflight + slow_count, DEV_INFLIGHT_CAP)
                while len(running) < cap:
                    try:
                        msg_str = redis_cli.lpop(self.queue_key)
                    except Exception as e:
                        logger.error("[%s] LPOP 失败: %s", self.dev_id, e)
                        break
                    if not msg_str:
                        break
                    try:
                        msg = json.loads(msg_str)
                    except Exception as e:
                        logger.error(
                            "[%s] account msg 解析失败 err=%s msg=%r",
                            self.dev_id, e, msg_str,
                        )
                        continue
                    running.add(executor.submit(self._process_msg, msg))

                if not running:
                    logger.warning(
                        "[%s] queue 已清空 + running=0,释放 claim,切换 dev",
                        self.dev_id,
                    )
                    drained_cleanly = True
                    break

                # 3) 等任意一个完成,timeout 让主 thread 周期性回顶 EXPIRE / progress。
                done, _ = wait(
                    running,
                    timeout=IDLE_CHECK_INTERVAL_SEC,
                    return_when=FIRST_COMPLETED,
                )
                running -= done
                # _process_msg 内部已包 try/except,future 不会向上抛。

                # 4) 周期性 progress:打 log + 写 mongo history.errors
                now = time.time()
                if now - last_progress_ts >= 60:
                    try:
                        pending = int(redis_cli.llen(self.queue_key))
                    except Exception:
                        pending = -1
                    self._write_progress(
                        RunStatus.STARTED, in_flight=len(running), pending=pending,
                    )
                    last_progress_ts = now
        finally:
            logger.warning(
                "[%s] worker 准备退出,等 in_flight=%d 跑完...",
                self.dev_id, len(running),
            )
            # 只 join 本 dev 自己 submit 的 futures,不动 executor
            for fut in running:
                try:
                    fut.result()
                except Exception:
                    pass
            # 子线程都结束 → buffer 里的尾批立即刷出,别滞留到下个 dev/进程退出
            try:
                flush_doris()
            except Exception:
                logger.exception("[%s] flush_doris 失败", self.dev_id)
            # 非 graceful 退出(LPOP 抛 / 主循环异常)保留 payload,
            # 等 TTL 自然过期 —— 否则 queue 里剩的 msg 下一个 worker 拉不到 payload 整批秒败。
            if drained_cleanly:
                self._finalize_history()
            try:
                redis_cli.delete(self.claim_key)
            except Exception:
                pass
            if self.review_lock_key:
                try:
                    redis_cli.delete(self.review_lock_key)
                except Exception:
                    pass

    def _advance_report_history(self) -> None:
        """读 dev_latest_history 指针;出现更新的 history 时把上报切过去:
        旧 history 写一次 ABORT 收尾后不再更新,计数清零,之后进度只写最新 history。
        指针由 dispatcher 每次分发更新,所以跨整点 worker 还在清积压时也能在 60s 内切走。
        只在主循环线程(_write_progress)调用,_report_history_id 单写者无竞争。"""
        try:
            raw = redis_cli.get(self.latest_history_key)
        except Exception as e:
            logger.error("[%s] 读 latest_history 指针失败: %s", self.dev_id, e)
            return
        latest = raw.decode() if isinstance(raw, bytes) else raw
        if not latest:
            return
        if self._report_history_id is None:
            self._report_history_id = latest
            return
        if latest == self._report_history_id:
            return
        old = self._report_history_id
        try:
            update_history_status(old, RunStatus.ABORT)
        except Exception as e:
            logger.error("[%s] 旧 history=%s 写 ABORT 失败: %s", self.dev_id, old, e)
        logger.warning("[%s] 上报 history 切换: %s -> %s (旧写 ABORT)", self.dev_id, old, latest)
        with self._progress_lock:
            self._processed_ok = 0
            self._processed_fail = 0
        self._report_history_id = latest

    def _account_kill_threshold_sec(self) -> int:
        """非 review 15min / review 40min。base_message 还没加载(没账户在跑)时按非 review。"""
        bm = self._base_message
        if bm and is_review(bm["date"]):
            return ACCOUNT_KILL_REVIEW_SEC
        return ACCOUNT_KILL_HOURLY_SEC

    def _write_progress(
        self, status: RunStatus, in_flight: int, pending: int,
    ) -> None:
        """打 log + 写 mongo errors;每 60s 一次 STARTED,退出时一次 COMPLETED。"""
        self._advance_report_history()
        ok = self._processed_ok
        fail = self._processed_fail
        total = ok + fail + in_flight + max(pending, 0)
        # in_flight<5 全部列出,否则只列超过 kill 阈值的慢户
        with self._inflight_lock:
            snapshot = [(acct, ts, tid) for acct, (ts, tid) in self._inflight_starts.items()]
        now = time.monotonic()
        elapsed = sorted(
            ((acct, now - ts, tid) for acct, ts, tid in snapshot),
            key=lambda x: -x[1],
        )
        # 超时账户直接往子线程注入异常,_process_one_account 的 except Exception 接住转 fail
        kill_threshold = self._account_kill_threshold_sec()
        for acct, sec, tid in elapsed:
            if sec > kill_threshold:
                self._kill_account_thread(acct, sec, tid)
        if len(elapsed) < 5:
            to_show = [(a, s) for a, s, _ in elapsed]
        else:
            to_show = [(a, s) for a, s, _ in elapsed if s > kill_threshold]
        detail = (
            " | " + ", ".join(f"{a}={s:.0f}s" for a, s in to_show)
            if to_show else ""
        )
        progress = (
            f"成功 {ok}/{total}, 排队中 {pending}, 正在执行 {in_flight}, 失败 {fail}{detail}"
        )
        report_id = self._report_history_id or self._history_id
        logger.info(
            "[%s] %s history_id=%s %s",
            self.dev_id, status.value, report_id, progress,
        )
        if report_id is None:
            return
        try:
            update_history_status(
                report_id, status,
                additional_fields={"errors": progress},
            )
        except Exception as e:
            logger.error(
                "[%s] 写 history 进度失败 status=%s history_id=%s: %s",
                self.dev_id, status.value, report_id, e,
            )

    def _kill_account_thread(self, account_id: str, elapsed_sec: float, tid: int) -> None:
        """SetAsyncExc 到子线程下个字节码边界生效;卡在 C 调用要等返回。每 60s 进度
        循环都会再发一次,直到线程退出并把 inflight 字典项 pop 掉。"""
        n = ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_ulong(tid), ctypes.py_object(AccountTimeoutKill),
        )
        if n == 0:
            logger.warning(
                "[%s] kill 超时账户失败 (tid 不存在) account=%s elapsed=%.0fs tid=%s",
                self.dev_id, account_id, elapsed_sec, tid,
            )
        elif n > 1:
            ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(tid), None)
            logger.error(
                "[%s] kill 超时账户异常 (影响多个线程,已撤回) account=%s tid=%s",
                self.dev_id, account_id, tid,
            )
        else:
            logger.warning(
                "[%s] kill 超时账户 account=%s elapsed=%.0fs tid=%s",
                self.dev_id, account_id, elapsed_sec, tid,
            )

    def _finalize_history(self) -> None:
        """退出收尾:写 COMPLETED + 清 dev_payload。没收到过任何消息时跳过。"""
        if self._history_id is None:
            return
        self._write_progress(RunStatus.COMPLETED, in_flight=0, pending=0)
        try:
            redis_cli.delete(REDIS_DEV_PAYLOAD_FMT.format(history_id=self._history_id))
        except Exception:
            pass


# ── dispatcher.run_dev_locally 的 inline drain 入口 ──

def _process_account_msg(dev_id: str, date: str, msg: Dict[str, Any]) -> None:
    """inline drain 用,同步跑完一条消息,不起 thread pool。"""
    worker = DevWorker(dev_id, date)
    worker._process_msg(msg)


# 容器认领的车道:hourly 只抢今天的队列、review 只抢历史日期的队列,从而给 hourly
# 预留专属容器(新 hourly 进来当场有 worker,不被 review 占满)。不设 = 抢全部(兼容旧部署)。
LANE = os.getenv("AD_SYNC_LANE")


def _lane_match(day: str) -> bool:
    if LANE == "hourly":
        return not is_review(day)
    if LANE == "review":
        return is_review(day)
    return True


def try_claim_dev() -> Optional[Tuple[str, str]]:
    """SCAN account_queue:* → 随机选一个 SETNX 抢锁。抢到返 (dev_id, date_prefix)。
    按 AD_SYNC_LANE 只看本车道的队列;review 日期额外抢 per-dev 串行锁,保证同 dev 一次只跑一天。
    """
    prefix = REDIS_ACCOUNT_QUEUE_FMT.split("{")[0]
    pattern = prefix + "*"
    pairs: list[Tuple[str, str]] = []
    for key in redis_cli.scan_iter(match=pattern, count=500):
        key_s = key.decode() if isinstance(key, bytes) else key
        rest = key_s[len(prefix):]
        if "|" not in rest:
            continue  # 老格式 key (没 date 段),切换期遗留,跳过等自然过期
        dev_id, day = rest.split("|", 1)
        if not _lane_match(day):
            continue
        pairs.append((dev_id, day))
    if not pairs:
        return None
    random.shuffle(pairs)
    for dev_id, day in pairs:
        review = is_review(day)
        if review and not redis_cli.set(
            REDIS_REVIEW_DEV_LOCK_FMT.format(dev_id=dev_id), "1",
            nx=True, ex=DEV_CLAIM_TTL_SEC,
        ):
            continue  # 同 dev 已有一天在跑,跳过它的其它天
        claim_key = REDIS_DEV_CLAIM_FMT.format(dev_id=dev_id, date=day)
        if redis_cli.set(claim_key, "1", nx=True, ex=DEV_CLAIM_TTL_SEC):
            logger.warning("[ad_sync_new] claim 到 dev_id=%s day=%s review=%s", dev_id, day, review)
            return dev_id, day
        # 没抢到 (dev, day) claim:把刚拿的 review 串行锁放回,换下一个
        if review:
            try:
                redis_cli.delete(REDIS_REVIEW_DEV_LOCK_FMT.format(dev_id=dev_id))
            except Exception:
                pass
    return None


# ── 主循环 ──────────────────────────────────────────────────────────────────

def _log_retry(retry_state):
    exception = retry_state.outcome.exception()
    err = "".join(
        traceback.format_exception(type(exception), exception, exception.__traceback__)
    )
    logger.error(
        "[ad_sync_new] account_consumer 第 %d 次失败,%ds 后重试: %s",
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
    """claim → run → shutdown → os._exit(0)。"""
    logger.warning(
        "[ad_sync_new] account_consumer (1 dev / process) 已启动,thread_pool 上限=%d",
        DEV_INFLIGHT_CAP,
    )
    while True:
        try:
            claim = try_claim_dev()
            if claim is None:
                time.sleep(IDLE_SLEEP_SEC)
                continue
            dev_id, date = claim
            try:
                qlen = int(redis_cli.llen(
                    REDIS_ACCOUNT_QUEUE_FMT.format(dev_id=dev_id, date=date)
                ))
            except Exception:
                qlen = 0
            max_inflight = min(
                DEV_THREADS_MIN + qlen // DEV_THREADS_PER_ACCOUNTS,
                DEV_INFLIGHT_CAP,
            )
            logger.warning(
                "[ad_sync_new] dev=%s 队列 %d 个 account → 基础线程数 %d",
                dev_id, qlen, max_inflight,
            )
            # max_workers 给到硬上限:慢户 boost 时 run() 会临时把 inflight 提到
            # max_inflight 之上;ThreadPoolExecutor 线程按需懒创建,不会白占
            executor = ThreadPoolExecutor(
                max_workers=DEV_INFLIGHT_CAP,
                thread_name_prefix="acct",
            )
            try:
                worker = DevWorker(dev_id, date)
                worker.run(executor, max_inflight=max_inflight)
            finally:
                executor.shutdown(wait=True)
            logger.warning(
                "[ad_sync_new] dev=%s 跑完,os._exit(0) 让 docker restart 重置 RSS",
                dev_id,
            )
            os._exit(0)
        except Exception as e:
            logger.error(
                "[ad_sync_new] 主循环逃出异常: %s\n%s",
                e, "\n".join(get_error()),
            )
            time.sleep(ERROR_BACKOFF_SEC)


if __name__ == "__main__":
    # service.name 带上 lane,让中央日志能区分 hourly / review 两个池;LANE 未设回退旧名。
    init(f"ad_sync_new_account_consumer_{LANE}" if LANE else "ad_sync_new_account_consumer")
    consumer_run()
