# -*- coding:utf-8 -*-
"""
Facebook Business Manager 消费者脚本 - 个人号级别处理

职责：
1. 从 Redis 队列拉取个人号信息（fb:business:sync:queue）
2. 初始化 Facebook API（使用个人号凭证）
3. 获取该个人号的所有 Business 列表并写入数据库
4. 对每个 Business 获取三类资源（Accounts/Pages/Pixels）
5. 处理完成后直接写入 MongoDB
"""

import json
import logging
import time

from facebook_business.api import FacebookSession, FacebookAdsApi
from facebook_business.adobjects.user import User
from facebook_business.exceptions import FacebookRequestError
from conf import Env, env
from conf.api_conf import get_proxies
from db.clients import mongo_client, mongo_client_user, redis_cli_2, tz_cst
from utils.common_util import fb_api_retry, handle_error
from utils.feishu import (
    ACCOUNT_UNBIND_CHAT_ID,
    PAY_ERROR_TEST_CHAT_ID,
    send_feishu_msg,
)
from datetime import datetime, timezone
from tasks.fb_business_sync.resource_fetcher import (
    fetch_bm_all,
    fetch_targeted_resources,
    fetch_user_resources,
    _sync_key,
)
from tasks.fb_business_sync.db_writer import upsert_personal_account
from model_type_defs.fb_asset_type import (
    FbSyncMessage,
    TokenType,
    SyncFlags,
    FB_BUSINESS_QUEUE_KEY,
)


class BusinessConsumer:
    """单条消息的处理器，每条消息创建一个实例。"""

    def __init__(self, message: FbSyncMessage):
        self.message = message
        self.doc_id: str = message["_id"]
        self.token_type: TokenType = message.get("token_type", TokenType.PERSONAL)

    def validate_message(self) -> bool:
        required_fields = ["_id", "app_id", "app_secret", "access_token"]
        for field in required_fields:
            if field not in self.message or not self.message[field]:
                logging.error(f"消息缺少必填字段: {field}")
                return False
        return True

    def _deactivate_personal_account(self, reason: str):
        """将失效凭证对应记录置为不可用。

        系统账号的 token 存在 accounts（按 app_id），个人号的 token 存在
        personal_accounts（按 _id）；状态字段类型不同：accounts 用 2（异常），personal_accounts 用 False。
        """
        if self.token_type == TokenType.SYSTEM_USER:
            # accounts.update_time 是后台写入的 CST 字符串，需与之保持同类型同时区
            collection, query = "accounts", {"app_id": self.doc_id}
            update = {
                "$set": {
                    "status": 2,
                    "update_time": datetime.now(tz_cst).strftime("%Y-%m-%d %H:%M:%S"),
                }
            }
        else:
            collection, query = "personal_accounts", {"_id": self.doc_id}
            update = {"$set": {"status": False, "updated_at": datetime.now(timezone.utc)}}
        doc = mongo_client[collection].find_one_and_update(query, update, upsert=False)
        logging.error(
            f"[{self.token_type} {self.doc_id}] 命中鉴权异常，"
            f"已将 {collection} 状态置为不可用，原因: {reason}"
        )
        if doc is None:
            return
        if self.token_type == TokenType.SYSTEM_USER:
            name = doc.get("description") or ""
            header = "⚠️系统开发者失效，请重新配置！"
            extra = f"✔️开发者ID：{doc.get('dev_id') or ''}\n"
        else:
            name = doc.get("name") or ""
            user = mongo_client_user["user"].find_one(
                {"real_name": doc.get("user_name")}, {"full_name": 1}
            )
            operator = user.get("full_name") if user else ""
            header = "⚠️账户授权失效，请重新授权！"
            extra = f"✔️投放师：{operator}\n"
        chat_id = ACCOUNT_UNBIND_CHAT_ID if env == Env.PROD else PAY_ERROR_TEST_CHAT_ID
        send_feishu_msg(
            f"{header}\n"
            f"✔️个号名称：{name}\n"
            f"✔️个号 ID：{self.doc_id}\n"
            f"{extra}"
            f"✔️时间：{datetime.now(tz_cst).strftime('%Y-%m-%d %H:%M:%S')}",
            chat_id,
        )

    def _should_deactivate_on_user_error(self, exc: Exception) -> bool:
        if not isinstance(exc, FacebookRequestError):
            return False

        code = None
        if hasattr(exc, "api_error_code") and callable(exc.api_error_code):
            code = exc.api_error_code()

        if hasattr(exc, "body") and callable(exc.body):
            body = exc.body()
            if isinstance(body, dict):
                err = body.get("error", {})
                code = err.get("code", code)

        # code=190 即 Token 失效大类，无论 subcode 均应禁用
        return code == 190

    @staticmethod
    @fb_api_retry
    def _probe_user_accounts():
        return User(fbid="me").get_ad_accounts(
            fields=["account_id"], params={"summary": "total_count"}
        )

    def _precheck_user_after_progress(self) -> bool:
        """前置账号可用性探测，可用时同时设置进度。"""
        try:
            user_account = self._probe_user_accounts()
            total = getattr(user_account, "_total_count", 0)

            redis_cli_2.set(
                _sync_key(self.doc_id), f"0/{total}", xx=True, keepttl=True
            )
            logging.info(
                f"[{self.token_type} {self.doc_id}] 进度初始化 total={total}, processed=0"
            )
            return True

        except Exception as e:
            if self._should_deactivate_on_user_error(e):
                self._deactivate_personal_account(str(e))
            logging.error(f"[{self.token_type} {self.doc_id}] 异常:", exc_info=True)
            return False

    def _release_sync_lock(self):
        redis_cli_2.delete(_sync_key(self.doc_id))
        logging.info(f"[{self.doc_id}] 已释放同步锁")

    def run(self):
        """处理单条消息。"""
        if not self.validate_message():
            return False

        try:
            acquired = redis_cli_2.set(
                _sync_key(self.doc_id), "0/0", nx=True, ex=3600
            )
            if not acquired:
                logging.info(f"跳过 {self.token_type} {self.doc_id}，已存在同步锁")
                return False

            proxies = get_proxies(self.message["proxy"])
            FacebookAdsApi.set_default_api(
                FacebookAdsApi(
                    FacebookSession(
                        self.message["app_id"],
                        self.message["app_secret"],
                        self.message["access_token"],
                        proxies=proxies,
                        timeout=(15, 180),
                    )
                )
            )
            logging.debug("  ✓ Facebook API 已初始化")

            if not self._precheck_user_after_progress():
                return None

            # 定向拉取:只拉指定资产,不走全量枚举
            targets = self.message.get("targets") or {}
            if targets.get("accounts") or targets.get("page_ids"):
                fetch_targeted_resources(self.message, targets)
                return True

            sync_flags = SyncFlags(**(self.message.get("sync_flags") or {}))

            # user + BM 的 accounts 收集到此容器，两者都跑完后一次性写入
            collected = {"accounts": []}

            if sync_flags.sync_personal:
                fetch_user_resources(self.message, collected)

            if sync_flags.sync_bm:
                fetch_bm_all(self.message, collected)

            accounts = list(
                {a["id"]: a for a in collected["accounts"]}.values()
            )
            if accounts:
                upsert_personal_account(
                    {
                        "_id": self.doc_id,
                        "token_type": self.token_type,
                        "data_type": "accounts",
                        "data": accounts,
                    }
                )

            return True
        finally:
            self._release_sync_lock()


@handle_error(error_message="Business 消费者异常")
def consume_loop():
    """主消费循环 - 持续从 Redis 队列阻塞式拉取任务。"""
    while True:
        try:
            result = redis_cli_2.blpop(FB_BUSINESS_QUEUE_KEY, timeout=30)
            if result is None:
                continue

            _, message_json = result
            message: FbSyncMessage = json.loads(message_json)
            logging.info(
                f"接收到任务 [{message.get('token_type')} {message.get('_id')}]"
            )

            consumer = BusinessConsumer(message)
            consumer.run()
        except Exception:
            logging.error("处理消息异常:", exc_info=True)
            time.sleep(5)


def business_consumer_worker():
    from conf.log_conf import init
    from utils.common import set_local_proxy

    set_local_proxy()
    init("fb_business_consumer")
    from tasks.fb_business_sync.account_ban_events import ensure_ban_event_indexes

    ensure_ban_event_indexes()
    consume_loop()


if __name__ == "__main__":
    business_consumer_worker()
