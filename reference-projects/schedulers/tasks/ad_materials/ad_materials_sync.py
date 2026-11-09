import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict

import requests

from conf.api_conf import backend_api
from conf.log_conf import init
from db.clients import mysql_client, mongo_client, redis_cli_1 as redis_cli
from model_type_defs.ad_materials_type import AD_MATERIALS_PRIMARY_FETCH_QUEUE_KEY
from utils.common import DayFormat
from utils.common_util import handle_error

# 字段配置常量（消除重复定义）
# 素材历史复用配置
UNIQUE_NAME_REUSE_CONFIG = {
    "enabled": True,           # 是否启用历史复用功能
    "lookback_days": 3,        # 向前查询天数(默认2天)
    "batch_size": 10000,         # 批量更新大小
}

FB_VIDEO_ERROR_KEY_PREFIX = "ad_materials:fb_video_error"
FB_VIDEO_ERROR_LOOKBACK_DAYS = 1

# 没匹配到平台/代理线的广告默认不拉素材, 但消耗前 N 的系列例外
TOP_SPEND_CAMPAIGN_LIMIT = 200

INSTALL_BASE_FIELDS = {
    "simple": {
        "select": """media_source,
            af_c_id as campaign_id,
            af_adset_id as ad_set_id,
            af_ad_id as ad_id,
            appsflyer_id""",
        "group": "media_source, af_c_id, af_adset_id, af_ad_id, appsflyer_id",
    },
    "full": {
        "select": """media_source,
            af_c_id as campaign_id,
            af_adset_id as ad_set_id,
            af_ad_id as ad_id,
            campaign as campaign_name,
            af_adset as ad_set_name,
            af_ad as ad_name,
            platform,
            appsflyer_id""",
        "group": "media_source, af_c_id, af_adset_id, af_ad_id, campaign, af_adset, af_ad, platform, appsflyer_id",
    },
}


def _build_recent_error_keys(days: int = FB_VIDEO_ERROR_LOOKBACK_DAYS):
    today = datetime.now()
    return [
        f"{FB_VIDEO_ERROR_KEY_PREFIX}:{(today - timedelta(days=i)).strftime('%Y%m%d')}"
        for i in range(days)
    ]


def _filter_ad_ids_by_fb_error_redis(missing_records: Dict[str, dict]) -> Dict[str, dict]:
    if not missing_records:
        return missing_records

    ad_ids = [str(ad_id) for ad_id in missing_records.keys()]
    keys = _build_recent_error_keys()

    try:
        pipe = redis_cli.pipeline()
        for ad_id in ad_ids:
            for key in keys:
                pipe.sismember(key, ad_id)
        checks = pipe.execute()

        hit_ad_ids = set()
        key_count = len(keys)
        for idx, ad_id in enumerate(ad_ids):
            start = idx * key_count
            end = start + key_count
            if any(checks[start:end]):
                hit_ad_ids.add(ad_id)

        filtered_records = {
            ad_id: record
            for ad_id, record in missing_records.items()
            if str(ad_id) not in hit_ad_ids
        }
        logging.info(
            f"Redis去重完成: 待下载 {len(missing_records)} -> 命中 {len(hit_ad_ids)} -> 实际下载 {len(filtered_records)}"
        )
        return filtered_records
    except Exception as redis_err:
        logging.error(f"Redis去重失败，降级为不过滤: {redis_err}")
        return missing_records


def _get_active_dev_ids(dev_ids) -> set:
    """返回启用状态的 dev_id 集合.

    - 不含 '_' 的 dev_id: accounts.status==1 即通过.
    - 含 '_' 的 dev_id (个号格式 "<前缀>_<personal_accounts._id>"):
      personal_accounts.status==True 且 personal.app_id 对应的 accounts.status==1 才通过.
    """
    if not dev_ids:
        return set()

    systemuser_dev_ids = {d for d in dev_ids if "_" not in d}
    personal_dev_ids = {d for d in dev_ids if "_" in d}

    enabled: set = set()

    if systemuser_dev_ids:
        enabled.update(
            doc["dev_id"]
            for doc in mongo_client["accounts"].find(
                {"dev_id": {"$in": list(systemuser_dev_ids)}, "status": 1},
                projection={"dev_id": 1},
            )
            if doc.get("dev_id")
        )

    if personal_dev_ids:
        personal_id_to_dev_id = {d.split("_", 1)[1]: d for d in personal_dev_ids}
        personal_docs = list(
            mongo_client["personal_accounts"].find(
                {"_id": {"$in": list(personal_id_to_dev_id.keys())}, "status": True},
                projection={"_id": 1, "app_id": 1},
            )
        )
        enabled_app_ids = {
            doc["app_id"]
            for doc in mongo_client["accounts"].find(
                {
                    "app_id": {"$in": list({p["app_id"] for p in personal_docs if p.get("app_id")})},
                    "status": 1,
                },
                projection={"app_id": 1},
            )
        } if personal_docs else set()
        for personal in personal_docs:
            if personal.get("app_id") not in enabled_app_ids:
                continue
            dev_id = personal_id_to_dev_id.get(str(personal["_id"]))
            if dev_id:
                enabled.add(dev_id)

    return enabled


def _build_account_id_aliases(account_id) -> set[str]:
    if not account_id:
        return set()
    return {str(account_id).strip().removeprefix("act_")}


def _load_personal_fetch_configs(account_ids: set[str]) -> dict[str, dict]:
    if not account_ids:
        return {}

    account_aliases = set()
    for account_id in account_ids:
        account_aliases.update(_build_account_id_aliases(account_id))

    personal_accounts = list(
        mongo_client["personal_accounts"].find(
            {"status": True, "accounts.id": {"$in": list(account_aliases)}},
            projection={
                "_id": 1,
                "app_id": 1,
                "access_token": 1,
                "updated_at": 1,
                "accounts": 1,
            },
        )
    )

    if not personal_accounts:
        return {}

    app_ids = {row.get("app_id") for row in personal_accounts if row.get("app_id")}
    app_configs = {
        row["app_id"]: row
        for row in mongo_client["accounts"].find(
            {"app_id": {"$in": list(app_ids)}, "status": 1},
            projection={"app_id": 1, "app_secret": 1, "proxy": 1},
        )
    }

    personal_accounts.sort(key=lambda row: str(row.get("updated_at") or ""))
    personal_fetch_configs = {}
    for personal_account in personal_accounts:
        app_id = personal_account.get("app_id")
        app_config = app_configs.get(app_id)
        if not app_config:
            continue

        fetch_config = {
            "source": "personal",
            "group_key": f"personal:{personal_account['_id']}",
            "app_id": app_id,
            "app_secret": app_config["app_secret"],
            "access_token": personal_account["access_token"],
            "proxy": app_config["proxy"],
        }
        for account in personal_account.get("accounts") or []:
            for alias in _build_account_id_aliases(account.get("id")):
                personal_fetch_configs[alias] = fetch_config
    return personal_fetch_configs


def _load_dev_fetch_configs(dev_ids: set[str]) -> dict[str, dict]:
    if not dev_ids:
        return {}

    systemuser_dev_ids = {d for d in dev_ids if "_" not in d}
    personal_dev_ids = {d for d in dev_ids if "_" in d}

    configs: dict[str, dict] = {}

    if systemuser_dev_ids:
        for dev in mongo_client["accounts"].find(
            {"dev_id": {"$in": list(systemuser_dev_ids)}, "status": 1},
            projection={
                "dev_id": 1,
                "app_id": 1,
                "app_secret": 1,
                "access_token": 1,
                "proxy": 1,
            },
        ):
            configs[dev["dev_id"]] = {
                "source": "dev",
                "group_key": f"dev:{dev['dev_id']}",
                "app_id": dev["app_id"],
                "app_secret": dev["app_secret"],
                "access_token": dev["access_token"],
                "proxy": dev["proxy"],
            }

    # 个号格式 dev_id: "<前缀>_<personal_accounts._id>"
    # access_token 走 personal_accounts, app_id/app_secret/proxy 用 personal.app_id 反查 accounts
    if personal_dev_ids:
        personal_id_to_dev_id = {d.split("_", 1)[1]: d for d in personal_dev_ids}
        personal_docs = list(
            mongo_client["personal_accounts"].find(
                {"_id": {"$in": list(personal_id_to_dev_id.keys())}, "status": True},
                projection={"_id": 1, "app_id": 1, "access_token": 1},
            )
        )
        app_ids = {p["app_id"] for p in personal_docs if p.get("app_id")}
        app_configs = {
            doc["app_id"]: doc
            for doc in mongo_client["accounts"].find(
                {"app_id": {"$in": list(app_ids)}, "status": 1},
                projection={"app_id": 1, "app_secret": 1, "proxy": 1},
            )
        } if app_ids else {}
        for personal in personal_docs:
            app_config = app_configs.get(personal.get("app_id"))
            dev_id = personal_id_to_dev_id.get(str(personal["_id"]))
            if not app_config or not dev_id:
                continue
            configs[dev_id] = {
                "source": "dev",
                "group_key": f"dev:{dev_id}",
                "app_id": personal["app_id"],
                "app_secret": app_config["app_secret"],
                "access_token": personal["access_token"],
                "proxy": app_config["proxy"],
            }

    return configs


PRIMARY_FETCH_CHUNK_SIZE = 10  # 与 fb_utils.download_ad_creatives_to_memory 的 batch_num 对齐

# 入队去重: 给每个 ad_id 在 Redis 占一把 SETNX 锁,防止 producer 频繁运行时重复入队.
# TTL 同时充当自愈机制: worker 崩溃/消息丢失,锁过期后允许重新入队.
# 调大 TTL 应对 worker 长时间积压,正常 worker 处理完 ad_materials 表会有记录,
# producer 的 LEFT JOIN 自然过滤,不会再走到入队逻辑.
FETCH_PENDING_LOCK_PREFIX = "ad_materials:fetch_pending:"
FETCH_PENDING_LOCK_TTL = 24 * 3600


def _claim_for_enqueue(ad_id: str) -> bool:
    """对 ad_id 抢占 SETNX 锁; True=首次入队, False=队列里已有未消费的同 ad_id"""
    return bool(redis_cli.set(
        f"{FETCH_PENDING_LOCK_PREFIX}{ad_id}",
        "1",
        nx=True,
        ex=FETCH_PENDING_LOCK_TTL,
    ))


def release_fetch_pending_locks(ad_ids) -> None:
    """
    worker 完成 Doris commit 后调用, 释放对应 ad_id 的入队锁.

    顺序铁律: 必须在 update_doris_unique_names_batch **成功之后** 才调,
    否则会出现 [DEL 锁 → producer 跑 → LEFT JOIN 仍 missing → 重新入队] 的竞态.

    单 key 串行 DEL: chunk 一般 ≤ 10, 一两次 round-trip 可忽略, 比批量 DEL 在
    弱网下更稳. DEL 失败仅打 warning, 锁会随 TTL 自然过期, 不影响主流程.
    """
    for ad_id in ad_ids:
        try:
            redis_cli.delete(f"{FETCH_PENDING_LOCK_PREFIX}{ad_id}")
        except Exception as e:
            logging.warning(f"释放 fetch_pending 锁失败 ad_id={ad_id}: {e}")


def _enqueue_missing_materials(missing_records: Dict[str, dict]) -> int:
    """
    将需要下载的素材按 fetch_config 分组后推入 Redis 主下载队列
    由独立 worker 进程消费,从而避免在单进程里多线程共享 FB SDK 全局 state

    Returns:
        成功推入队列的广告数(未解析到 fetch_config 的跳过)
    """
    if not missing_records:
        logging.info("没有需要下载的素材")
        return 0

    account_ids = {
        record["account_id"]
        for record in missing_records.values()
        if record.get("account_id")
    }
    personal_fetch_configs = _load_personal_fetch_configs(account_ids)

    dev_ids = {
        record["dev_id"] for record in missing_records.values() if record.get("dev_id")
    }
    dev_fetch_configs = _load_dev_fetch_configs(dev_ids)

    fetch_groups = defaultdict(list)
    group_configs = {}
    unresolved = 0
    deduped = 0
    for ad_id, record in missing_records.items():
        fetch_config = None
        account_id = record.get("account_id")
        if account_id:
            for alias in _build_account_id_aliases(account_id):
                fetch_config = personal_fetch_configs.get(alias)
                if fetch_config:
                    logging.info(
                        f"素材下载命中个号: account_id={account_id}, group_key={fetch_config['group_key']}, ad_id={ad_id}"
                    )
                    break

        if not fetch_config:
            fetch_config = dev_fetch_configs.get(record.get("dev_id"))

        if not fetch_config:
            unresolved += 1
            continue

        # 抢占去重锁: 队列里已有未消费的同 ad_id 时跳过,
        # 允许 producer 高频运行而不重复入队
        if not _claim_for_enqueue(ad_id):
            deduped += 1
            continue

        fetch_groups[fetch_config["group_key"]].append((ad_id, record))
        group_configs[fetch_config["group_key"]] = fetch_config

    sorted_groups = sorted(fetch_groups.items(), key=lambda kv: -len(kv[1]))
    total = sum(len(recs) for _, recs in sorted_groups)
    logging.info(
        f"=== 生产者入队 === 共 {total} 个广告分 {len(sorted_groups)} 组, "
        f"无 fetch_config 跳过 {unresolved} 个, 队列已存在跳过 {deduped} 个"
    )

    enqueued = 0
    for group_key, ad_records in sorted_groups:
        logging.info(f"  {group_key:<40} {len(ad_records)} 个")
        fetch_config = group_configs[group_key]
        for i in range(0, len(ad_records), PRIMARY_FETCH_CHUNK_SIZE):
            chunk = ad_records[i: i + PRIMARY_FETCH_CHUNK_SIZE]
            payload = {
                "group_key": group_key,
                "fetch_config": fetch_config,
                "ad_records": [
                    {
                        "ad_id": str(ad_id),
                        "unique_name": record.get("unique_name", ""),
                        "account_id": str(record.get("account_id") or ""),
                        "dev_id": str(record.get("dev_id") or ""),
                        "game_platform": record.get("game_platform", ""),
                        "ad_platform": record.get("ad_platform", ""),
                        "unique_key_fields": record.get("unique_key_fields", {}),
                    }
                    for ad_id, record in chunk
                ],
            }
            redis_cli.rpush(
                AD_MATERIALS_PRIMARY_FETCH_QUEUE_KEY,
                json.dumps(payload, ensure_ascii=False, default=str),
            )
            enqueued += len(chunk)

    return enqueued


def _save_material_sync(file_content: bytes, unique_name: str, metadata: dict, extension: str = "jpg"):
    """
    通过调用 backend 内部接口保存素材

    Args:
        file_content: 文件二进制内容
        unique_name: 唯一名称（basename）
        metadata: 其他元数据
        extension: 文件扩展名（默认 "jpg"）
    """

    # 检查是否已存在
    existing = mongo_client["materials"].find_one({"basename": unique_name})
    if existing:
        logging.info(f"素材 {unique_name} 已存在，跳过")
        return

    # 推断文件扩展名
    if not extension:
        extension = "jpg"
    
    filename = f"{unique_name}.{extension}"
    mime_type = "video/mp4" if extension == "mp4" else "image/jpeg"

    # 准备表单数据
    files = {"file": (filename, file_content, mime_type)}

    data = {
        "filename": filename,
    }

    # 添加可选元数据
    if metadata.get("game_platform"):
        data["game_platform"] = metadata["game_platform"]
    if metadata.get("ad_platform"):
        data["ad_platform"] = metadata["ad_platform"]
    if metadata.get("country"):
        data["country"] = metadata["country"]
    if metadata.get("category"):
        data["category"] = metadata["category"]

    # 调用内部接口
    try:
        response = requests.post(
            f"{backend_api}/materials/internal", files=files, data=data, timeout=20
        )
        response.raise_for_status()

        result = response.json()
        if result.get("code") == 0:
            logging.debug(f"素材 {unique_name} 上传成功")
            return result["data"][0]["basename"]
        else:
            raise Exception(f"上传失败: {result.get('message')}")

    except requests.exceptions.RequestException as e:
        logging.error(f"调用 backend 接口失败: {e}")
        raise


def update_doris_unique_names_batch(update_dict: Dict[tuple, str]) -> None:
    """
    批量更新 Doris ad_daily_detail 和 ad_hourly_detail 表的 unique_name 字段
    对于 ad_hourly_detail：按日期匹配当天所有小时的记录

    Args:
        update_dict: 更新字典，格式: {unique_key_tuple: new_unique_name, ...}
                    unique_key_tuple = (date, ad_platform, timezone_name,
                                       account_id, campaign_id, ad_set_id, ad_id)

    Returns:
        无
    """
    if not update_dict:
        logging.info("没有需要更新的记录")
        return

    def format_value(v):
        """将值格式化为 SQL 识别的格式
        - None 转换为 NULL
        - 空字符串转换为 NULL
        """
        # 检查 None 或空字符串
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return "NULL"
        # 转义单引号并加引号
        safe_v = str(v).replace("'", "\\'")
        return f"'{safe_v}'"

    def build_condition(field_name, value):
        """构建条件语句，处理 NULL 值的比较
        NULL 值用 IS NULL，非 NULL 值用 = 比较
        """
        formatted = format_value(value)
        if formatted == "NULL":
            return f"{field_name} IS NULL"
        else:
            return f"{field_name} = {formatted}"

    with mysql_client.session() as cur:
        cur.execute("SET enable_unique_key_partial_update = true")
        cur.execute("SET enable_insert_strict = false")

        # 按表分别处理
        for table_name in ("ad_hourly_detail", "ad_daily_detail"):
            case_conditions = []
            all_ad_ids = set()

            # 第一步：构建所有的 CASE WHEN 条件
            for key_tuple, new_name in update_dict.items():
                # key_tuple = (date, ad_platform, timezone_name,
                #              account_id, campaign_id, ad_set_id, ad_id)
                date_val = key_tuple[0]
                ad_platform, timezone_name, account_id, campaign_id, ad_set_id, ad_id = key_tuple[1:]

                # 获取日期部分（统一为 YYYY-MM-DD 格式）
                if hasattr(date_val, 'strftime'):
                    date_str = date_val.strftime('%Y-%m-%d')
                else:
                    date_str = str(date_val)[:10]

                all_ad_ids.add(ad_id)

                # 根据表类型构建不同的 WHEN 条件
                if table_name == "ad_hourly_detail":
                    # 对于 hourly 表，按日期范围匹配当天所有小时
                    when_condition = f"""WHEN DATE(`date`) = {format_value(date_str)} AND
                        {build_condition('ad_platform', ad_platform)} AND
                        {build_condition('timezone_name', timezone_name)} AND
                        {build_condition('account_id', account_id)} AND
                        {build_condition('campaign_id', campaign_id)} AND
                        {build_condition('ad_set_id', ad_set_id)} AND
                        {build_condition('ad_id', ad_id)}
                        THEN {format_value(new_name)}"""
                else:
                    # 对于 daily 表，直接按日期匹配
                    when_condition = f"""WHEN `date` = {format_value(date_str)} AND
                        {build_condition('ad_platform', ad_platform)} AND
                        {build_condition('timezone_name', timezone_name)} AND
                        {build_condition('account_id', account_id)} AND
                        {build_condition('campaign_id', campaign_id)} AND
                        {build_condition('ad_set_id', ad_set_id)} AND
                        {build_condition('ad_id', ad_id)}
                        THEN {format_value(new_name)}"""

                case_conditions.append(when_condition)

            if not case_conditions:
                continue

            # 第二步：构建 CASE WHEN 语句
            case_statement = "CASE\n" + "\n".join(case_conditions) + "\nELSE unique_name END"

            # 第三步：构建 WHERE 条件，限制 ad_id 范围以避免更新整个表
            ad_ids_list = [format_value(ad_id) for ad_id in all_ad_ids]
            ad_ids_condition = ", ".join(ad_ids_list)

            # 第四步：执行批量 UPDATE
            update_sql = f"""
            UPDATE {table_name}
            SET unique_name = {case_statement}
            WHERE ad_id IN ({ad_ids_condition})
            """

            try:
                execute_count = cur.execute(update_sql)
                logging.info(f"{table_name} 批量更新完成，共更新 {execute_count} 条记录")
            except Exception as e:
                logging.error(f"Doris 批量更新 {table_name} 失败: {e}")

    logging.info("Doris unique_name 更新完成")


def sync_unique_names_to_doris(unique_names: list) -> int:
    """
    将 unique_names 写入 Doris ad_materials 表

    Args:
        unique_names: unique_name 列表

    Returns:
        写入的行数
    """
    if not unique_names:
        logging.info("没有需要写入 Doris 的 unique_name")
        return 0

    # 构建 VALUES 子句
    values_list = [f"('{name}')" for name in unique_names]
    values_str = ", ".join(values_list)

    sql_insert = f"""
INSERT INTO ad_materials (unique_name) VALUES {values_str};
"""
    with mysql_client.session() as cur:
        cur.execute("SET enable_unique_key_partial_update = true")
        cur.execute("SET enable_insert_strict = false")
        execute_count = cur.execute(sql_insert)
    logging.info(f"写入 ad_materials 表完成，共 {execute_count} 条数据")
    return execute_count


def _batch_update_unique_names(table_name: str, records: tuple, batch_size: int, date_expr_fn) -> int:
    """
    通过 Doris 部分列更新(INSERT)批量更新 unique_name

    原理：INSERT 主键已存在的行时，开启 partial update 模式后
    Doris 只更新 INSERT 中指定的列（unique_name），其余列保持不变
    """
    updated_count = 0
    with mysql_client.session() as cur:
        cur.execute("SET enable_unique_key_partial_update = true")
        cur.execute("SET enable_insert_strict = false")

        for i in range(0, len(records), batch_size):
            batch = records[i: i + batch_size]
            values_list = []

            for row in batch:
                (curr_date, _, ad_platform, _, timezone_name,
                 account_id, campaign_id, ad_set_id, ad_id, _, _, _, historical_unique_name) = row

                date_val = date_expr_fn(curr_date)
                safe_name = str(historical_unique_name).replace("'", "\\'")
                values_list.append(
                    f"({date_val}, '{ad_platform}', '{timezone_name}', "
                    f"'{account_id}', '{campaign_id}', '{ad_set_id}', '{ad_id}', '{safe_name}')"
                )

            values_str = ", ".join(values_list)
            sql_insert = f"""
INSERT INTO {table_name} (date, ad_platform, timezone_name,
    account_id, campaign_id, ad_set_id, ad_id, unique_name)
VALUES {values_str};"""

            try:
                batch_updated = cur.execute(sql_insert)
                updated_count += batch_updated
                logging.info(f"批次 {i // batch_size + 1}: 更新{table_name} {batch_updated} 条记录")
            except Exception as e:
                logging.error(f"批次 {i // batch_size + 1} 更新{table_name}失败: {e}")

    return updated_count


def _apply_reusable_records(reusable_records: tuple, batch_size: int) -> tuple[int, int]:
    """对查到的 reusable 记录执行: daily 去重写入 + hourly 写入 + ad_materials 写入

    records 列结构: (date, game_platform, ad_platform, agent_line, timezone_name,
        account_id, campaign_id, ad_set_id, ad_id, ad_name, unique_name, china_date,
        historical_unique_name)
    返回: (daily_updated_count, hourly_updated_count)
    """
    if not reusable_records:
        return 0, 0

    # daily 表 DATE 匹配, 按 (日期, 维度) 去重避免一天写多次同一行
    def daily_date_expr(d):
        return f"'{d.strftime(DayFormat) if hasattr(d, 'strftime') else str(d)[:10]}'"
    seen_daily_keys = set()
    daily_deduped = []
    for row in reusable_records:
        curr_date = row[0]
        daily_date = curr_date

        # 仅处理 00 点数据: daily 归到前一天
        if hasattr(curr_date, "hour"):
            if curr_date.hour == 0:
                daily_date = curr_date - timedelta(days=1)
            date_str = daily_date.strftime(DayFormat)
        else:
            date_str = daily_date.strftime(DayFormat)
            daily_date = date_str

        key = (date_str,) + row[1:9]
        if key not in seen_daily_keys:
            seen_daily_keys.add(key)
            daily_deduped.append((daily_date,) + row[1:])
    daily_count = _batch_update_unique_names(
        "ad_daily_detail", tuple(daily_deduped), batch_size, daily_date_expr
    )

    # hourly 表 DATETIME 精确匹配
    def hourly_date_expr(d):
        return f"'{d}'"
    hourly_count = _batch_update_unique_names(
        "ad_hourly_detail", reusable_records, batch_size, hourly_date_expr
    )

    # 复用的 unique_name 同步登记到 ad_materials
    reused_unique_names = {row[-1] for row in reusable_records}
    if reused_unique_names:
        try:
            sync_unique_names_to_doris(list(reused_unique_names))
            logging.info(f"已将 {len(reused_unique_names)} 个复用的unique_name写入ad_materials表")
        except Exception as e:
            logging.error(f"写入ad_materials失败: {e}")

    return daily_count, hourly_count


def reuse_historical_unique_names(hours: int = 3, lookback_days: int = 2) -> int:
    """实现 unique_name 复用, 两条独立路径:

    路径1: 同维度键自连接 — 同一广告(account/campaign/adset/ad 相同)历史上有过
        真实素材名, 现在被重置为 ad_name 时, 把历史值拿回来
    路径2: post_id 跨广告 — is_original=False 的"跑原帖"广告, 找同 post_id
        的兄弟行(原帖或其他跑原帖的广告)已设的 unique_name, 直接复用

    补数范围是整个 lookback 窗口(幂等自愈): 名字晚于行出现(素材下载管道
    次日才回填)时, 下一跑仍能补齐; 事件时间小窗口会永久漏掉这类行。

    Args:
        hours: 已废弃, 仅为兼容旧调度调用保留
        lookback_days: 向前查询天数(默认2天)

    Returns:
        hourly 表合计更新的记录数量
    """
    logging.info(f"开始 unique_name 复用 (向前{lookback_days}天全窗口)")
    batch_size = UNIQUE_NAME_REUSE_CONFIG["batch_size"]
    total_hourly = 0

    # ---- 路径1: 同维度键自连接复用 ----
    # curr: lookback 窗口内 unique_name 为空或 = ad_name（未设素材）
    # hist: 同维度下 ad_name != unique_name（已有素材），lookback_days天内
    sql_find_reusable = f"""
SELECT * FROM (
    SELECT
        date, game_platform, ad_platform, agent_line, timezone_name,
        account_id, campaign_id, ad_set_id, ad_id, ad_name, unique_name,
        china_date,
        MAX(CASE WHEN ad_name != unique_name THEN unique_name END)
            OVER(PARTITION BY ad_platform, timezone_name, account_id, campaign_id, ad_set_id, ad_id)
            as historical_unique_name
    FROM ad_hourly_detail
    WHERE china_date >= DATE_SUB(CURDATE(), INTERVAL {lookback_days} DAY)
) t
WHERE (unique_name IS NULL OR ad_name = unique_name)
  AND t.historical_unique_name IS NOT NULL
"""
    try:
        records = mysql_client.read(sql_find_reusable)
    except Exception as e:
        logging.error(f"路径1 查询失败: {e}")
        records = ()

    if records:
        logging.info(f"路径1: 找到 {len(records)} 条可复用记录")
        d, h = _apply_reusable_records(records, batch_size)
        logging.info(f"路径1 完成: daily={d}, hourly={h}")
        total_hourly += h
    else:
        logging.info("路径1: 未找到可复用的历史 unique_name")

    # ---- 路径2: post_id 跨广告复用(仅 is_original=False) ----
    # 跑原帖的广告自己没素材名, 但同 post_id 的兄弟行可能已有, 直接复用
    sql_find_by_post_id = f"""
SELECT
    a.date, a.game_platform, a.ad_platform, a.agent_line, a.timezone_name,
    a.account_id, a.campaign_id, a.ad_set_id, a.ad_id, a.ad_name, a.unique_name,
    a.china_date,
    b.unique_name AS historical_unique_name
FROM ad_hourly_detail a
JOIN (
    SELECT post_id, unique_name,
           ROW_NUMBER() OVER (PARTITION BY post_id ORDER BY date DESC) AS rn
    FROM ad_hourly_detail
    WHERE post_id IS NOT NULL
      AND unique_name IS NOT NULL
      AND ad_name != unique_name
      AND china_date >= DATE_SUB(CURDATE(), INTERVAL {lookback_days} DAY)
) b ON a.post_id = b.post_id AND b.rn = 1
WHERE a.china_date >= DATE_SUB(CURDATE(), INTERVAL {lookback_days} DAY)
  AND a.is_original = 0
  AND a.post_id IS NOT NULL
  AND (a.unique_name IS NULL OR a.ad_name = a.unique_name)
"""
    try:
        records = mysql_client.read(sql_find_by_post_id)
    except Exception as e:
        logging.error(f"路径2 查询失败: {e}")
        records = ()

    if records:
        logging.info(f"路径2: 找到 {len(records)} 条 post_id 可复用记录")
        d, h = _apply_reusable_records(records, batch_size)
        logging.info(f"路径2 完成: daily={d}, hourly={h}")
        total_hourly += h
    else:
        logging.info("路径2: 未找到 post_id 可复用的 unique_name")

    logging.info(f"复用结束, hourly 累计 {total_hourly} 条")
    return total_hourly


@handle_error()
def write_ad_materials(day=1):
    """
    主函数：同步广告素材数据
    - 查询在 Doris 但不在 ad_materials 中的 unique_name
    - 区分两类：已在 MongoDB materials 中的、不在 MongoDB materials 中的
    - 对不在 MongoDB 的：下载素材并保存
    - 对已在 MongoDB 的：直接写入 Doris ad_materials 表
    """
    logging.info("任务执行开始write_ad_materials")

    # 第一步：查询差集（在 ad_daily_detail 中存在但不在 ad_materials 中的记录）
    # 同时获取 unique_name、ad_id、dev_id 以及 UNIQUE KEY 的所有字段
    logging.info("开始查询待处理的广告素材")
    # TODO 后续要做成没有gameplat_form的也要拉取, 并且只处理is_original true的, false的直接改成true相同的值
    # agent_line 和 game_platform 由 backfill_agent_line_by_url.py 异步回填,
    # 不能放进 GROUP BY (否则同一行在回填前后会被当作不同记录,导致计数膨胀)。
    # 用 MAX 聚合取任一非空值即可。
    # 拉取范围: 已匹配平台/代理线(game_platform 非空)的广告,
    # 或当天消耗前 TOP_SPEND_CAMPAIGN_LIMIT 的系列下的广告(game_platform 为 null 的也拉)
    sql_query = f"""
SELECT
    d.date,
    MAX(d.game_platform) AS game_platform,
    d.ad_platform,
    MAX(d.agent_line) AS agent_line,
    d.timezone_name,
    d.account_id,
    d.campaign_id,
    d.ad_set_id,
    d.ad_id,
    d.dev_id,
    d.unique_name
FROM ad_daily_detail d
LEFT JOIN ad_materials m ON d.unique_name = m.unique_name
WHERE m.unique_name IS NULL
  AND d.date >= DATE_SUB(CURDATE(), INTERVAL {day} DAY)
  AND d.unique_name IS NULL
  AND d.amount_spent > 10
  AND d.ad_id IS NOT NULL
  AND (
    d.game_platform IS NOT NULL
    OR d.campaign_id IN (
        SELECT campaign_id
        FROM ad_daily_detail
        WHERE date = CURDATE()
          AND campaign_id IS NOT NULL
        GROUP BY campaign_id
        ORDER BY SUM(amount_spent) DESC
        LIMIT {TOP_SPEND_CAMPAIGN_LIMIT}
    )
  )
  AND d.is_original IS TRUE
GROUP BY d.date, d.ad_platform, d.timezone_name,
         d.account_id, d.campaign_id, d.ad_set_id, d.ad_id, d.dev_id, d.unique_name
ORDER BY d.date DESC;
"""
    diff_results = mysql_client.read(sql_query)

    if not diff_results:
        logging.info("没有需要同步的广告素材")
        return

    # 预加载启用状态的 dev_id 集合: 把已禁用开发者下的广告直接过滤掉,
    # 不再让它们污染后续 MongoDB 查询 / 入队日志统计.
    dev_ids_in_rows = {row[9] for row in diff_results if row[9]}
    enabled_dev_ids = _get_active_dev_ids(dev_ids_in_rows)

    # 构建字典：{ad_id: {"unique_name": ..., "dev_id": ..., "unique_key_fields": {...}, ...}}
    ad_records = {}
    unique_names_all = []
    skipped_disabled_rows = 0
    skipped_disabled_dev_ids: set = set()
    for row in diff_results:
        (
            ad_date,
            game_platform,
            ad_platform,
            agent_line,
            timezone_name,
            account_id,
            campaign_id,
            ad_set_id,
            ad_id,
            dev_id,
            unique_name,
        ) = row

        if dev_id not in enabled_dev_ids:
            skipped_disabled_rows += 1
            skipped_disabled_dev_ids.add(dev_id)
            continue

        unique_names_all.append(unique_name)
        ad_records[ad_id] = {
            "unique_name": unique_name,
            "account_id": account_id,
            "dev_id": dev_id,
            "game_platform": game_platform,
            "ad_platform": ad_platform,
            "unique_key_fields": {
                "date": ad_date,
                "game_platform": game_platform,
                "ad_platform": ad_platform,
                "agent_line": agent_line,
                "timezone_name": timezone_name,
                "account_id": account_id,
                "campaign_id": campaign_id,
                "ad_set_id": ad_set_id,
                "ad_id": ad_id,
            },
        }

    if skipped_disabled_rows:
        logging.info(
            f"开发者已禁用,跳过 {skipped_disabled_rows} 行, "
            f"涉及 dev_id ({len(skipped_disabled_dev_ids)} 个): "
            f"{sorted(skipped_disabled_dev_ids)}"
        )
    logging.info(f"从 Doris 查询到 {len(unique_names_all)} 个待同步的 unique_name")

    # 第二步：去 MongoDB 查询这些 unique_name 是否在 materials collection 的 basename 字段中存在
    materials_collection = mongo_client["materials"]
    existing_basenames = set(
        materials_collection.distinct(
            "basename", {"basename": {"$in": unique_names_all}}
        )
    )
    total_synced_to_mongo = len(existing_basenames)
    enqueued_count = 0

    # 第三步：取差集 - 找出不在 MongoDB 中的素材,入队由 worker 异步下载
    unique_names_set = set(unique_names_all)
    missing_basenames = unique_names_set - existing_basenames

    if missing_basenames:
        missing_records = {
            ad_id: record
            for ad_id, record in ad_records.items()
            if record["unique_name"] in missing_basenames
        }

        # Redis 近5天去重: 过滤 FacebookRequestError 已命中的 ad_id
        missing_records = _filter_ad_ids_by_fb_error_redis(missing_records)
        if not missing_records:
            logging.info("Redis去重后没有需要下载的素材,跳过入队")
        else:
            enqueued_count = _enqueue_missing_materials(missing_records)

    # 第四步：将所有在 MongoDB 中存在的 unique_name 写入 Doris ad_materials 表
    # 本次新下载的素材由 worker 保存到 MongoDB 后,下次 write_ad_materials 再同步到 ad_materials
    if existing_basenames:
        execute_count = sync_unique_names_to_doris(list(existing_basenames))
        logging.info(f"同步广告素材累计历史数据完毕,共写入 {execute_count} 条数据")
    else:
        logging.info("没有素材需要写入 Doris ad_materials 表")

    logging.info(
        f"=== write_ad_materials 执行完成 === "
        f"Doris 查询 {len(unique_names_all)} 个 unique_name, "
        f"MongoDB 中已有 {total_synced_to_mongo} 个, "
        f"本次生产者新入队总数 {enqueued_count} 个待下载"
    )


def check_no_img():
    read = mysql_client.read("select unique_name from ad_materials")
    names = [i[0] for i in read]
    cursor = (
        mongo_client["materials"]
        .find({"basename": {"$in": names}}, projection={"_id": 0, "basename": 1})
    )
    existing = {doc["basename"] for doc in cursor}
    missing = set(names) - existing
    print(missing)


def log_unfilled_summary(hours: int = 6) -> None:
    """打印近 hours 小时 unique_name 仍未填充的行分布,
    按 is_original / 是否有 post_id 分桶,定位漏网之鱼"""
    sql = f"""
SELECT
    COUNT(*) AS cnt,
    is_original,
    CASE WHEN post_id IS NULL THEN 1 ELSE 0 END AS no_post
FROM ad_hourly_detail
WHERE china_date >= DATE_SUB(NOW(), INTERVAL {hours} HOUR)
  AND (unique_name IS NULL OR ad_name = unique_name)
GROUP BY is_original, CASE WHEN post_id IS NULL THEN 1 ELSE 0 END
ORDER BY cnt DESC
"""
    try:
        rows = mysql_client.read(sql)
    except Exception as e:
        logging.error(f"查询未填充摘要失败: {e}")
        return

    logging.info(f"=== 近 {hours}h unique_name 未填充摘要 ===")
    if not rows:
        logging.info("  全部填充完成,无漏网")
        return

    is_orig_label = {1: "原帖", 0: "跑原帖", None: "未知"}
    total = 0
    for cnt, is_original, no_post in rows:
        total += cnt
        post_label = "无post_id" if no_post else "有post_id"
        logging.info(
            f"  {is_orig_label.get(is_original, str(is_original))} / {post_label}: {cnt} 行"
        )
    logging.info(f"  合计: {total} 行")


if __name__ == "__main__":
    init("ad_materials_sync")
    # 先 reuse: 库内闭环复用,廉价
    reuse_historical_unique_names()
    # 再 fetch: 把剩下的 unique_name 入队下载素材
    # write_ad_materials()
    # 最后打印剩余漏网情况,定位需要人工介入的边界
    # log_unfilled_summary()
