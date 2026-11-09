# -*- coding:utf-8 -*-
"""
FB 素材推送消费者

职责：
1. 从 Redis 队列拉取推送任务（fb:material:push:queue，backend /materials/fb_push 投递）
2. 初始化 Facebook API（消息自带 token/proxy）
3. 逐素材经 backend url_by_basename 取预签名 URL；图片下载到本地临时文件后上传，
   视频直接把 URL 交给 FB 拉取（对齐 ad_operation.publisher.upload_media）
4. 每个素材完成后回填进度到 Redis；成功项写 mongo fb_material_uploads 并记一天去重 key
"""

import base64
import json
import logging
import shutil
import time
from datetime import datetime, timezone
import tempfile
from pathlib import Path
import requests
from bson import ObjectId
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adimage import AdImage
from facebook_business.adobjects.advideo import AdVideo
from facebook_business.api import FacebookSession, FacebookAdsApi
from urllib.parse import urlparse
from conf.api_conf import get_proxies, backend_api
from db.clients import mongo_client, redis_cli_2
from utils.common_util import fb_api_retry, handle_error

QUEUE_KEY = "fb:material:push:queue"
TASK_TTL = 24 * 60 * 60

uploads_col = mongo_client["fb_material_uploads"]
orders_col = mongo_client["material_orders"]


def _task_key(task_id: str) -> str:
    return f"fb:material:push:task:{task_id}"


def _dedup_key(target_type: str, target_id: str, basename: str) -> str:
    return f"fb:material:push:dedup:{target_type}:{target_id}:{basename}"


def _fb_filename(url: str, basename: str) -> str:
    """FB 素材库显示名。basename 不带后缀,从 URL 补上(图片还靠它判文件类型)。"""
    return f"{basename}{Path(urlparse(url).path).suffix}"


def _cleanup_tmp(path: str):
    # ignore_errors: SDK 报错路径会泄漏文件句柄(见 api.py open_files)，Windows 下删不掉
    shutil.rmtree(Path(path).parent, ignore_errors=True)


class MaterialPushConsumer:
    """单条推送任务的处理器，每条消息创建一个实例。"""

    def __init__(self, message: dict):
        self.message = message
        self.task_id = message["task_id"]
        self.target_type = message["target_type"]
        self.target_id = message["target_id"]
        self.personal_id = message["personal_id"]
        self.order_id = message.get("order_id")
        self.proxy = message.get("proxy")
        self.succeeded_basenames: set = set()

    def _set_order_status(self, status: str):
        if self.order_id:
            orders_col.update_one(
                {"_id": ObjectId(self.order_id)},
                {"$set": {"fb_push_status": status}},
            )

    def _update_order_failed(self, succeeded: set, failed: set):
        """维护 material_orders.fb_push_failed:失败待重传列表,每条
        {target_type, target_id, basename},前端按它重新发起推送。
        本次成功的条目移除、失败的写入;列表清空后置 null。"""
        if not self.order_id or not (succeeded or failed):
            return
        doc = orders_col.find_one(
            {"_id": ObjectId(self.order_id)}, {"fb_push_failed": 1}
        ) or {}
        entries = [
            e for e in (doc.get("fb_push_failed") or [])
            if not (
                e.get("target_type") == self.target_type
                and e.get("target_id") == self.target_id
                and e.get("basename") in succeeded | failed
            )
        ]
        entries += [
            {
                "target_type": self.target_type,
                "personal_id": self.personal_id,
                "target_id": self.target_id,
                "basename": b,
            }
            for b in sorted(failed)
        ]
        orders_col.update_one(
            {"_id": ObjectId(self.order_id)},
            {"$set": {"fb_push_failed": entries or None}},
        )

    def _load_progress(self) -> dict:
        raw = redis_cli_2.get(_task_key(self.task_id))
        if raw:
            return json.loads(raw)
        return {
            "status": "processing",
            "total": len(self.message["materials"]),
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "items": [],
        }

    def _save_progress(self, progress: dict):
        redis_cli_2.set(
            _task_key(self.task_id),
            json.dumps(progress, ensure_ascii=False),
            ex=TASK_TTL,
        )

    def _fetch_material_url(self, basename: str) -> str:
        response = None
        for attempt in range(3):
            try:
                response = requests.get(
                    f"{backend_api}/materials/url_by_basename/{basename}",
                    timeout=30,
                )
                response.raise_for_status()
                break
            except requests.exceptions.RequestException:
                if attempt == 2:
                    raise
                logging.warning(
                    f"url_by_basename请求失败，第{attempt + 1}次重试", exc_info=True
                )
        data = response.json()
        if data["code"] != 0:
            raise ValueError(f'调用url_by_basename报错: {data["message"]}')
        return data["data"]["url"]

    def _download_to_tmp(self, url: str, basename: str) -> str:
        resp = requests.get(url, proxies=get_proxies(self.proxy), timeout=120)
        resp.raise_for_status()
        # FB 素材库名称取自上传的文件名,故用独立临时目录承载它
        path = Path(tempfile.mkdtemp()) / _fb_filename(url, basename)
        path.write_bytes(resp.content)
        return str(path)

    @fb_api_retry
    def _upload_image(self, url: str, basename: str) -> str:
        tmp_path = self._download_to_tmp(url, basename)
        try:
            image = AdAccount(f"act_{self.target_id}").create_ad_image(
                params={"filename": tmp_path}
            )
            return image[AdImage.Field.hash]
        finally:
            _cleanup_tmp(tmp_path)

    @fb_api_retry
    def _upload_video(self, url: str, basename: str) -> str:
        # 视频不落本地,FB 侧直接按 URL 拉取(对齐 ad_operation.publisher.upload_media)
        video = AdAccount(f"act_{self.target_id}").create_ad_video(
            params={"file_url": url, "name": _fb_filename(url, basename)}
        )
        return video[AdVideo.Field.id]

    def _process_materials(self):
        progress = self._load_progress()
        progress["status"] = "processing"
        self._save_progress(progress)

        failed_basenames: set = set()
        for m in self.message["materials"]:
            basename = m["basename"]
            try:
                url = self._fetch_material_url(basename)
                if m["filetype"] == "image":
                    fb_asset_id = self._upload_image(url, basename)
                else:
                    fb_asset_id = self._upload_video(url, basename)
                now = datetime.now(timezone.utc)
                uploads_col.update_one(
                    {
                        "target_id": self.target_id,
                        "target_type": self.target_type,
                        "basename": basename,
                    },
                    {
                        "$set": {
                            "fb_asset_id": fb_asset_id,
                            "filetype": m["filetype"],
                            "updated_at": now,
                        },
                        "$setOnInsert": {"created_at": now},
                    },
                    upsert=True,
                )
                redis_cli_2.set(
                    _dedup_key(self.target_type, self.target_id, basename),
                    "1",
                    ex=TASK_TTL,
                )
                item = {
                    "basename": basename,
                    "status": "success",
                    "fb_asset_id": fb_asset_id,
                }
                progress["succeeded"] += 1
                self.succeeded_basenames.add(basename)
                logging.info(f"[{self.task_id}] {basename} 上传成功: {fb_asset_id}")
            except Exception as e:
                logging.error(f"[{self.task_id}] {basename} 上传失败:", exc_info=True)
                item = {"basename": basename, "status": "failed", "error": str(e)}
                progress["failed"] += 1
                failed_basenames.add(basename)
            progress["processed"] += 1
            progress["items"].append(item)
            self._save_progress(progress)

        progress["status"] = "done"
        self._save_progress(progress)
        # 终态按 items 全量判定（含 backend 预填的 skipped/failed 项）
        statuses = {i["status"] for i in progress["items"]}
        if "failed" not in statuses:
            final = "done"
        elif statuses & {"success", "skipped"}:
            final = "partial"
        else:
            final = "failed"
        self._set_order_status(final)
        self._update_order_failed(self.succeeded_basenames, failed_basenames)

    def run(self):
        try:
            FacebookAdsApi.set_default_api(
                FacebookAdsApi(
                    FacebookSession(
                        self.message["app_id"],
                        self.message["app_secret"],
                        self.message["access_token"],
                        proxies=get_proxies(self.proxy),
                        timeout=(15, 180),
                    )
                )
            )
            self._process_materials()
        except Exception as e:
            logging.error(f"[{self.task_id}] 任务异常:", exc_info=True)
            progress = self._load_progress()
            progress["status"] = "done"
            progress["error"] = str(e)
            self._save_progress(progress)
            self._set_order_status("failed")
            # 任务级异常:没成功的素材全部记入待重传列表
            all_basenames = {m["basename"] for m in self.message.get("materials", [])}
            self._update_order_failed(
                self.succeeded_basenames, all_basenames - self.succeeded_basenames
            )
        finally:
            # 任务结束释放指纹，允许同批素材重新发起（一天内未成功项可重推）
            if self.message.get("fp_key"):
                redis_cli_2.delete(self.message["fp_key"])


@handle_error(error_message="素材推送消费者异常")
def consume_loop():
    """主消费循环 - 持续从 Redis 队列阻塞式拉取任务。"""
    while True:
        try:
            result = redis_cli_2.blpop(QUEUE_KEY, timeout=30)
            if result is None:
                continue

            _, message_json = result
            message: dict = json.loads(message_json)
            logging.info(
                f"接收到推送任务 [{message.get('task_id')}] "
                f"{message.get('target_type')} {message.get('target_id')} "
                f"共 {len(message.get('materials', []))} 个素材"
            )
            MaterialPushConsumer(message).run()
        except Exception:
            logging.error("处理消息异常:", exc_info=True)
            time.sleep(5)


def material_push_consumer_worker():
    from conf.log_conf import init
    from utils.common import set_local_proxy

    set_local_proxy()
    init("fb_material_push_consumer")
    consume_loop()


if __name__ == "__main__":
    material_push_consumer_worker()
