"""
广告素材主下载 worker (Redis 队列消费者)

消费 AD_MATERIALS_PRIMARY_FETCH_QUEUE_KEY,每条消息是同一个 fetch_config (group) 下
的一批广告 (默认 10 条),与 fb_utils 的 batch_num 对齐。

流程:
1. BLPOP 一条消息
2. 调用 download_ad_creatives_to_memory(ad_ids, fetch_config) — SDK 批量拉 creative
3. 成功 → _save_material_sync 保存到 MongoDB
4. 失败 (没有可下载 URL) → rpush 到 AD_CREATIVE_FETCH_QUEUE_KEY,由 scrape_worker 用 Playwright 兜底
5. 本批全部处理完后,一次性 update_doris_unique_names_batch 更新 Doris unique_name

设计要点: 每个 worker 进程独占 FB SDK 全局 state (FacebookAdsApi.set_default_api),
不需要线程池和锁,横向扩并发直接加进程数即可。

用法:
    python -m tasks.ad_materials.ad_materials_fetch_worker
"""

import json
import logging
import time
import traceback
from typing import Optional

from conf.log_conf import init
from db.clients import redis_cli_1 as redis_cli
from model_type_defs.ad_materials_type import (
    AD_CREATIVE_FETCH_QUEUE_KEY,
    AD_MATERIALS_PRIMARY_FETCH_QUEUE_KEY,
    AdMaterialsPrimaryFetchMessage,
)
from tasks.ad_materials.ad_materials_sync import (
    _save_material_sync,
    release_fetch_pending_locks,
    update_doris_unique_names_batch,
)
from utils.fb_utils import download_ad_creatives_to_memory, install_fb_usage_backoff

init("ad_materials_fetch_worker")

BLPOP_TIMEOUT_SECONDS = 5


def _pop_one(
    queue_name: str = AD_MATERIALS_PRIMARY_FETCH_QUEUE_KEY,
    timeout: int = BLPOP_TIMEOUT_SECONDS,
) -> Optional[AdMaterialsPrimaryFetchMessage]:
    try:
        result = redis_cli.blpop(queue_name, timeout=timeout)
    except Exception as e:
        logging.error(f"Redis BLPOP 异常: {e}")
        time.sleep(1)
        return None

    if not result:
        return None

    _, payload = result
    try:
        return json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else payload)
    except Exception as e:
        logging.error(f"消息 JSON 解析失败: {e}, raw={payload!r}")
        return None


def _push_scrape_fallback(ad_id: str, record: dict, fetch_config: dict):
    fields = record.get("unique_key_fields", {}) or {}
    redis_cli.rpush(
        AD_CREATIVE_FETCH_QUEUE_KEY,
        json.dumps({
            "ad_id": str(ad_id),
            "account_id": str(fields.get("account_id") or record.get("account_id") or ""),
            "dev": fetch_config,
            "metadata": {
                "unique_name": record.get("unique_name", ""),
                "date": str(fields.get("date", "")),
                "ad_platform": fields.get("ad_platform", ""),
                "timezone_name": fields.get("timezone_name", ""),
                "campaign_id": str(fields.get("campaign_id", "")),
                "ad_set_id": str(fields.get("ad_set_id", "")),
            },
        }, ensure_ascii=False, default=str),
    )


def process_ad_batch(
    fetch_config: dict,
    ad_records: list,
    group_key: str = "manual",
) -> None:
    """
    业务核心: SDK 拉素材 → 存 Mongo → 批量更新 Doris,失败 rpush 给 Playwright 兜底。
    与 Redis 队列解耦,直接传业务参数即可调用(本地调试 / 单测 / 一次性补数都走这里)。

    Args:
        fetch_config: {app_id, app_secret, access_token, proxy, ...}
        ad_records: [{ad_id, unique_name, account_id, dev_id, game_platform,
                     ad_platform, unique_key_fields}, ...]
        group_key: 仅用于日志归类
    """
    if not fetch_config.get("access_token") or not ad_records:
        logging.error(f"[{group_key}] 缺必要字段,丢弃")
        return

    ad_id_to_record = {str(r["ad_id"]): r for r in ad_records}
    ad_ids = list(ad_id_to_record.keys())

    logging.info(f"[{group_key}] 开始处理 {len(ad_ids)} 个素材")

    update_dict: dict[tuple, str] = {}
    successful_ad_ids: list[str] = []

    try:
        for ad_id, file_content, extension in download_ad_creatives_to_memory(
            ad_ids, fetch_config
        ):
            ad_id = str(ad_id)
            record = ad_id_to_record.get(ad_id, {})

            if not file_content:
                logging.warning(f"[{group_key}] {ad_id} SDK 未抓到媒体,转 Playwright 兜底")
                _push_scrape_fallback(ad_id, record, fetch_config)
                continue

            unique_name = record.get("unique_name") or f"ad_{ad_id}"
            try:
                new_name = _save_material_sync(
                    file_content, unique_name, record, extension
                )
            except Exception as e:
                logging.error(f"[{group_key}] {ad_id} ({unique_name}) 保存 Mongo 失败: {e}")
                continue

            if not new_name:
                logging.info(f"[{group_key}] {ad_id} ({unique_name}) 未拿到 saved_name,跳过 Doris")
                continue

            fields = record.get("unique_key_fields") or {}
            unique_key_tuple = (
                fields.get("date"),
                fields.get("ad_platform"),
                fields.get("timezone_name"),
                fields.get("account_id"),
                fields.get("campaign_id"),
                fields.get("ad_set_id"),
                fields.get("ad_id") or ad_id,
            )
            update_dict[unique_key_tuple] = new_name
            successful_ad_ids.append(ad_id)
            logging.info(f"[{group_key}] ✅ {ad_id} ({unique_name} -> {new_name}) 保存成功")

    except Exception as e:
        logging.error(f"[{group_key}] 批量下载异常: {e}")
        traceback.print_exc()

    if update_dict:
        try:
            update_doris_unique_names_batch(update_dict)
            logging.info(f"[{group_key}] Doris 批量更新完成: {len(update_dict)} 条")
            # Doris commit 成功后才释放锁: 此时 producer LEFT JOIN 已能过滤这些 ad_id,
            # 即便锁立即被删, 下次 producer 也不会重复入队
            release_fetch_pending_locks(successful_ad_ids)
        except Exception as e:
            logging.error(f"[{group_key}] Doris 批量更新失败: {e}")


def main():
    # 主下载 worker: 高用量时让 SDK call 自己 sleep 退避,保护账户配额
    install_fb_usage_backoff(auto_sleep=True)
    logging.info(
        f"启动 ad_materials_fetch_worker, queue={AD_MATERIALS_PRIMARY_FETCH_QUEUE_KEY}"
    )
    while True:
        msg = _pop_one()
        if not msg:
            continue
        try:
            process_ad_batch(
                fetch_config=msg.get("fetch_config") or {},
                ad_records=msg.get("ad_records") or [],
                group_key=msg.get("group_key") or "unknown",
            )
        except Exception as e:
            logging.error(f"处理消息异常: {e}")
            traceback.print_exc()


if __name__ == "__main__":
    main()
