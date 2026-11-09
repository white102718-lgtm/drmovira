import datetime
import json
import logging
import os
import random
import socket
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from bson import ObjectId
from facebook_business import FacebookSession
from facebook_business.adobjects.ad import Ad
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adset import AdSet
from facebook_business.adobjects.campaign import Campaign
from facebook_business.api import FacebookAdsApi
from facebook_business.exceptions import FacebookRequestError

from conf.api_conf import get_proxies
from conf.log_conf import init
from db.clients import redis_cli_3 as operation_redis, mongo_client_user, mysql_client
from model_type_defs.ad_operation_type import (
    OpType,
    OperationFields,
)
from tasks.ad_operation.common import (
    AD_OP_CAMPAIGN_SYNC_QUEUE_KEY,
    AD_OP_DEV_CLAIM_TEMPLATE,
    AD_OP_DEV_QUEUE_PREFIX,
    AD_OP_ROUTE_PENDING_KEY,
    compact_for_log,
    dev_lane_key,
    dev_queue_key,
    extract_error_message,
)
from tasks.ad_operation.publisher import AdPublisher
from tasks.ad_operation.risk_control import _release_lock, reserve_operation_slot
from tasks.ad_operation.storage import (
    get_account_id_by_level,
    get_dev_app_by_account_id,
    save_message,
    update_status,
)
from utils.common import LEVEL, RunStatus
from utils.message_signing import verify_signature

init("op_consumer")


OBJECT_CLASS_MAPPING = {
    LEVEL.campaign.value: Campaign,
    LEVEL.adset.value: AdSet,
    LEVEL.ad.value: Ad,
    LEVEL.account.value: AdAccount,
}

# FB 临时错误(is_transient / 5xx)重试;CREATE 不重试
TRANSIENT_RETRY_ATTEMPTS = 3
TRANSIENT_RETRY_SLEEP_SEC = 15


def _build_op_key(message_data: OperationFields) -> str:
    op_type = OpType(message_data["type"])
    if op_type == OpType.CREATE:
        return f"{message_data['_id']}:{op_type.value}"
    return f"{message_data['level']}:{message_data['id']}:{op_type.value}"



class Operation:
    def __init__(self, message_data: OperationFields = None):
        self.data = message_data
        self.dev = self.data["dev_app"]
        self.level = self.data.get("level")
        self.api: FacebookAdsApi | None = None

    @property
    def fb_object(self):
        obj_class = OBJECT_CLASS_MAPPING.get(self.level)
        if not obj_class:
            raise ValueError(f"不支持的广告级别: {self.level}")
        if self.api is None:
            raise RuntimeError("Facebook API 尚未初始化")
        return (
            obj_class(self.data.get("id"), api=self.api)
            if self.data.get("id")
            else obj_class(api=self.api)
        )

    def _update_budget(self):
        if self.level not in [LEVEL.campaign.value, LEVEL.adset.value]:
            raise Exception(f"不支持{self.level}级别的预算更新")
        result = self.fb_object.api_update(params={"daily_budget": self.data["value"]})
        logging.info(
            f"update_budget success level={self.level} id={self.data.get('id')} "
            f"target_daily_budget={self.data['value']} "
            f"api_update_result={result}"
        )

    def _update_state(self, state: Literal["ACTIVE", "PAUSED"]):
        result = self.fb_object.api_update(params={"status": state})
        logging.info(
            f"_update_state success level={self.level} state={state} "
            f"id={self.data.get('id')} "
            f"api_update_result={result}"
        )

    def _delete(self):
        self.fb_object.api_delete()

    def _create(self):
        if self.api is None:
            raise RuntimeError("Facebook API 尚未初始化")
        last_exception = None
        for config in self.data["create_config"]:
            try:
                AdPublisher(self.dev, config, self.api, self.data).publish()
            except Exception as e:
                last_exception = e
                logging.error(
                    f"执行创建时报错, 跳过进行下一个: {traceback.format_exc()}"
                )
        if last_exception:
            raise last_exception

    def create_fb_api(self) -> FacebookAdsApi:
        """为本条消息创建独立 API，禁止写 SDK 进程全局 default API。

        同一 app_id 可携带不同 token 并发执行；default API 是类级可变状态，任一
        线程覆盖后都会让其它线程的请求串用 token。所有 SDK 对象须显式绑定本实例。
        """
        session = FacebookSession(
            self.dev["app_id"],
            self.dev["app_secret"],
            self.dev["access_token"],
            proxies=get_proxies(self.dev["proxy"]),
        )
        return FacebookAdsApi(session)

    def process_message(self):
        self.api = self.create_fb_api()
        op_handlers = {
            OpType.BUDGET: self._update_budget,
            OpType.PAUSE: lambda: self._update_state("PAUSED"),
            OpType.START: lambda: self._update_state("ACTIVE"),
            OpType.DELETE: self._delete,
            OpType.CREATE: self._create,
        }
        handler = op_handlers.get(self.data["type"])
        if not handler:
            raise ValueError(f"不支持的操作类型: {self.data['type']}")
        if self.data["type"] == OpType.CREATE.value:
            # 创建不重试:临时错误下可能已建成,重试会出重复广告
            handler()
            return
        for attempt in range(1, TRANSIENT_RETRY_ATTEMPTS + 1):
            try:
                handler()
                return
            except FacebookRequestError as e:
                transient = e.api_transient_error() or e.http_status() in (500, 503)
                if not transient or attempt == TRANSIENT_RETRY_ATTEMPTS:
                    raise
                logging.warning(
                    f"FB 临时错误, {TRANSIENT_RETRY_SLEEP_SEC}s 后重试 "
                    f"{attempt}/{TRANSIENT_RETRY_ATTEMPTS - 1} level={self.level} "
                    f"id={self.data.get('id')} type={self.data['type']}: "
                    f"{extract_error_message(e)}"
                )
                time.sleep(TRANSIENT_RETRY_SLEEP_SEC)


class OpTracker:
    """统一操作进度/锁追踪器，所有 OpType 共用一条逻辑"""

    PREFIX = "ad_op"

    def __init__(self, op_key: str, op_type: OpType, *, value=None, ttl: int = 3600):
        self.redis_key = f"{self.PREFIX}:{op_key}"
        self.op_type = op_type
        self.value = value
        self.ttl = ttl

    def _build_payload(self, status: RunStatus, error: str | None = None) -> str:
        return json.dumps(
            {
                "op_type": self.op_type.value,
                "status": status.value,
                "value": self.value,
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "error": error,
            },
            ensure_ascii=False,
        )

    def set_status(self, status: RunStatus, error: str | None = None):
        operation_redis.set(
            self.redis_key,
            self._build_payload(status, error),
            ex=self.ttl,
        )

    def __enter__(self):
        raw = operation_redis.get(self.redis_key)
        if raw and json.loads(raw).get("status") == RunStatus.STARTED.value:
            raise RuntimeError(f"操作已在执行中: {self.redis_key}")
        self.set_status(RunStatus.STARTED)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        "操作广告状态回写的：广告面板状态查询用，不可动"
        if exc_type:
            self.set_status(RunStatus.FAILED, extract_error_message(exc_val))
        else:
            self.set_status(RunStatus.COMPLETED)
        return False


def _resolve_user(user_id: str = None, api_key: str = None) -> dict | None:
    """通过 user_id 或 api_key 查询用户，返回 {real_name, department} 或 None"""
    user_col = mongo_client_user["user"]
    if user_id:
        return user_col.find_one(
            {"_id": ObjectId(user_id)}, {"real_name": 1, "department": 1}
        )
    if api_key:
        return user_col.find_one(
            {"api_keys.key": api_key}, {"real_name": 1, "department": 1}
        )
    return None


def _check_permission(level: str, entity_id: str, department: str) -> bool:
    """通过该实体下所有广告的部门，校验用户是否有权操作"""
    id_col = {
        "campaign": "campaign_id",
        "adset": "ad_set_id",
        "ad": "ad_id",
    }.get(level)
    if not id_col or not department:
        return False
    rows = mysql_client.read(
        f"SELECT DISTINCT department FROM ad_daily_detail "
        f"WHERE level = 'ad' AND {id_col} = '{entity_id}'"
    )
    departments = {r[0] for r in rows} if rows else set()
    if department in departments:
        return True
    # 技术部可操作无限部的广告
    return department == "技术部" and "无限部" in departments


def _mirror_op_failed(message_data: OperationFields, error: str | None) -> None:
    """失败回写 redis ad_op（面板 operate_status 查询用）。
    仅当该 key 还是提交占位 PENDING 或不存在时才写 FAILED，避免覆盖 tracker 已写的终态或另一次执行的 STARTED。"""
    level = message_data.get("level")
    obj_id = message_data.get("id")
    op_type = message_data.get("type")
    if not level or not obj_id or not op_type:
        return
    try:
        tracker = OpTracker(
            f"{level}:{obj_id}:{op_type}", OpType(op_type), value=message_data.get("value")
        )
        raw = operation_redis.get(tracker.redis_key)
        if raw and json.loads(raw).get("status") != "PENDING":
            return
        tracker.set_status(RunStatus.FAILED, error)
    except Exception as e:
        logging.error(f"_mirror_op_failed 回写失败: {e}")


_DORIS_SYNC_OP_TYPES = {
    OpType.BUDGET.value,
    OpType.PAUSE.value,
    OpType.START.value,
    OpType.DELETE.value,
}


def _enqueue_campaign_sync(saved: OperationFields) -> None:
    """操作成功后推队列,由 campaign_sync_consumer 定向同步该系列。
    失败只记日志,半点全量同步兜底。CREATE 不触发。"""
    if saved.get("type") not in _DORIS_SYNC_OP_TYPES:
        return
    ext_info = saved.get("ext_info") or {}
    campaign_id = (
        saved.get("id") if saved.get("level") == LEVEL.campaign.value
        else ext_info.get("campaign_id")
    )
    account_id = ext_info.get("account_id")
    if not campaign_id or not account_id:
        logging.warning(
            f"跳过系列定向同步: 缺 campaign_id/account_id, ext_info={ext_info}"
        )
        return
    try:
        operation_redis.rpush(
            AD_OP_CAMPAIGN_SYNC_QUEUE_KEY,
            json.dumps(
                {
                    "account_id": account_id,
                    "campaign_id": campaign_id,
                    "dev_app": saved["dev_app"],
                },
                ensure_ascii=False,
                default=str,
            ),
        )
    except Exception:
        logging.error("推送系列定向同步队列失败(半点全量兜底):", exc_info=True)


def _run_with_tracker(message_data: OperationFields):
    """统一入口：save_message → 用户/权限校验 → acquire lock → 执行 → 释放锁 + 更新状态"""
    try:
        # 用户身份解析 —— 在入库前完成，让 save_message 直接带上操作人
        user = _resolve_user(
            user_id=message_data.get("user_id"),
            api_key=message_data.get("api_key"),
        )
        message_data["real_name"] = user["real_name"] if user else "未知用户"

        saved = save_message(message_data)
        if saved is None:
            return

        if not saved.get("auto_run", False):
            return

        # 身份校验
        if not user:
            err_msg = "无法识别用户身份，终止执行"
            logging.error(err_msg)
            update_status(saved["_id"], RunStatus.FAILED, err_msg)
            _mirror_op_failed(message_data, err_msg)
            return

        # 部门权限校验（CREATE 类型无 level/id，跳过）
        level = saved.get("level")
        entity_id = saved.get("id")
        if (
            level
            and entity_id
            and not _check_permission(level, entity_id, user.get("department"))
        ):
            err_msg = f"权限不足: {saved['real_name']} 无权操作 {level}:{entity_id}"
            logging.error(err_msg)
            update_status(saved["_id"], RunStatus.FAILED, err_msg)
            _mirror_op_failed(message_data, err_msg)
            return

        execute_at = reserve_operation_slot(operation_redis, saved["dev_app"])
        wait_seconds = execute_at - time.time()
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        op_key = _build_op_key(saved)
        op_type = OpType(saved["type"])
        tracker = OpTracker(op_key, op_type, value=saved.get("value"))

        with tracker:
            Operation(message_data=saved).process_message()

        message_str = json.dumps(saved, ensure_ascii=False, default=str)
        logging.info(f"执行结束: {compact_for_log(message_str)}")
        update_status(saved["_id"], RunStatus.COMPLETED)
        _enqueue_campaign_sync(saved)
    except Exception as e:
        logging.error("处理消息时发生错误:", exc_info=True)
        if message_data.get("_id"):
            update_status(
                message_data["_id"],
                RunStatus.FAILED,
                traceback.format_exc(),
            )
        _mirror_op_failed(message_data, extract_error_message(e))


MAX_INFLIGHT = 5  # 单开发者并发上限
CREATE_MAX_INFLIGHT = 4  # create 最多占 4 个槽,给快操作(暂停/预算等)留 1 个
CLAIM_TTL_SEC = 30
IDLE_SLEEP_SEC = 3
DEV_IDLE_RELEASE_SEC = 30  # 队列空置多久后释放该开发者
POLL_INTERVAL_SEC = 0.3
ROUTE_BATCH = 20


def _route_pending():
    """把提交侧不知道开发者的消息按 account 反查后转发到对应 dev 队列。
    只做路由不改消息本体(改了会破坏签名),dev_app 由执行时 save_message 再补。"""
    for _ in range(ROUTE_BATCH):
        raw = operation_redis.lpop(AD_OP_ROUTE_PENDING_KEY)
        if raw is None:
            return
        try:
            message = json.loads(raw)
            app_id = (message.get("dev_app") or {}).get("app_id")
            if not app_id:
                level, obj_id = message.get("level"), message.get("id")
                account_id = (
                    get_account_id_by_level(level, obj_id) if level and obj_id else None
                )
                dev_app = (
                    get_dev_app_by_account_id(account_id.removeprefix("act_"))
                    if account_id
                    else None
                )
                app_id = dev_app.get("app_id") if dev_app else None
            if not app_id:
                err = f"路由失败: 未找到 {message.get('level')}={message.get('id')} 对应的开发者配置"
                logging.error(err)
                if message.get("_id"):
                    update_status(message["_id"], RunStatus.FAILED, err)
                _mirror_op_failed(message, err)
                continue
            operation_redis.rpush(dev_queue_key(app_id, message.get("type")), raw)
        except Exception:
            logging.error(f"route_pending 消息处理失败,丢弃: {raw[:500]}", exc_info=True)


def _try_claim_dev(worker_token: str) -> str | None:
    """SCAN 非空 dev 队列 → 随机挑一个 SETNX 抢占,同一开发者同时只有一个进程执行。"""
    dev_ids = set()
    for key in operation_redis.scan_iter(match=f"{AD_OP_DEV_QUEUE_PREFIX}*", count=500):
        key_s = key.decode() if isinstance(key, bytes) else key
        dev_ids.add(key_s[len(AD_OP_DEV_QUEUE_PREFIX):].rsplit(":", 1)[0])
    dev_ids = list(dev_ids)
    random.shuffle(dev_ids)
    for app_id in dev_ids:
        claim_key = AD_OP_DEV_CLAIM_TEMPLATE.format(app_id=app_id)
        if operation_redis.set(claim_key, worker_token, nx=True, ex=CLAIM_TTL_SEC):
            logging.info(f"claim 到开发者 app_id={app_id}")
            return app_id
    return None


class DevWorker:
    """独占一个开发者,fast 队列优先于 create,线程池并发执行。"""

    def __init__(self, app_id: str, worker_token: str):
        self.app_id = app_id
        self.worker_token = worker_token
        self.claim_key = AD_OP_DEV_CLAIM_TEMPLATE.format(app_id=app_id)
        self.fast_key = dev_lane_key(app_id, "fast")
        self.create_key = dev_lane_key(app_id, "create")

    def _pop(self, create_inflight: int):
        raw = operation_redis.lpop(self.fast_key)
        if raw is not None:
            return raw, "fast"
        if create_inflight < CREATE_MAX_INFLIGHT:
            raw = operation_redis.lpop(self.create_key)
            if raw is not None:
                return raw, "create"
        return None, None

    def run(self):
        executor = ThreadPoolExecutor(
            max_workers=MAX_INFLIGHT, thread_name_prefix=f"op_{self.app_id}"
        )
        futures: dict = {}  # future -> "fast" | "create"
        idle_since = None
        try:
            while True:
                operation_redis.expire(self.claim_key, CLAIM_TTL_SEC)
                futures = {f: lane for f, lane in futures.items() if not f.done()}
                raw, lane = None, None
                if len(futures) < MAX_INFLIGHT:
                    create_inflight = sum(
                        1 for v in futures.values() if v == "create"
                    )
                    raw, lane = self._pop(create_inflight)
                if raw is not None:
                    idle_since = None
                    message_str = (
                        raw.decode("utf-8") if isinstance(raw, bytes) else raw
                    )
                    try:
                        logging.info(
                            f"收到消息 app_id={self.app_id}: {compact_for_log(message_str)}"
                        )
                        message_data: OperationFields = json.loads(message_str)
                        if not verify_signature(
                            message_data, message_data.get("api_key")
                        ):
                            logging.error(
                                f"消息验签失败，丢弃: {compact_for_log(message_str)}"
                            )
                            continue
                        futures[executor.submit(_run_with_tracker, message_data)] = lane
                    except Exception:
                        logging.error(
                            f"消息处理失败，丢弃: {compact_for_log(message_str)}",
                            exc_info=True,
                        )
                    continue
                if futures:
                    idle_since = None
                elif idle_since is None:
                    idle_since = time.time()
                elif time.time() - idle_since > DEV_IDLE_RELEASE_SEC:
                    logging.info(f"开发者 app_id={self.app_id} 队列空置,释放")
                    return
                time.sleep(POLL_INTERVAL_SEC)
        finally:
            executor.shutdown(wait=True)
            _release_lock(operation_redis, self.claim_key, self.worker_token)


def op_consumer():
    worker_token = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
    logging.info(f"op_consumer 启动 (1 进程 1 开发者), token={worker_token}")
    while True:
        try:
            _route_pending()
            app_id = _try_claim_dev(worker_token)
            if app_id is None:
                time.sleep(IDLE_SLEEP_SEC)
                continue
            DevWorker(app_id, worker_token).run()
            logging.info(f"开发者 app_id={app_id} 服务完成, os._exit(0) 交给 docker 重启")
            os._exit(0)
        except Exception:
            logging.error("主循环异常:", exc_info=True)
            time.sleep(IDLE_SLEEP_SEC)


if __name__ == "__main__":
    op_consumer()
