from collections import defaultdict
from enum import Enum

from app.db.clients import redis_cli_3
from app.model_type_defs.ad_operation import OpType


class RowStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    STARTED = "started"
    PENDING = "pending"


def detect_create_stage(data: dict) -> str | None:
    """按 create_config 字段特征识别 create 三阶段；非 create 返回 None。

    - 有 campaigns → campaign（系列）
    - 无 campaigns、有 adset_id → ad（广告）
    - 无 campaigns、有 campaign_id → adset（组）
    """
    if data.get("type") not in {OpType.CREATE, OpType.CREATE.value}:
        return None
    configs = data.get("create_config") or []
    if not configs:
        return None
    sample = configs[0]
    if sample.get("campaigns"):
        return "campaign"
    if sample.get("adset_id"):
        return "ad"
    if sample.get("campaign_id"):
        return "adset"
    return None


def _stage_node(name: str | None, doc: dict | None) -> dict:
    """节点构造助手：挂 name + 当前阶段 doc 的 status/error/stage_id（doc 缺省为占位）。"""
    return {
        "name": name,
        "status": doc.get("status") if doc else None,
        "error": doc.get("error") if doc else None,
        "stage_id": doc["_id"] if doc else None,
    }


def _build_full_item(campaign_doc: dict) -> dict:
    """系列 doc → mode=full 合并 item 骨架（accounts → campaigns → adsets → ads）。

    整条 doc 失败且错误能定位到本 doc 内某个户时,只有命中户的系列挂 FAILED+error;
    其它户的系列先占位并标记,留待 _resolve_marked_campaigns 按是否有组 doc 回填状态。
    """
    data = campaign_doc.get("data") or {}
    configs = data.get("create_config") or []
    err_acc = campaign_doc.get("error_account_id")
    acc_norms = {(c.get("account_id") or "").removeprefix("act_") for c in configs}
    split = campaign_doc.get("status") == "FAILED" and err_acc in acc_norms
    # 开发者级错误(token失效)下,被 split 留给 adset 判定的户里,凡是没建成的都因同一
    # 原因失败,把该错误一并带给它们;账户级错误则不外溢,留空交给 _resolve_marked_campaigns。
    dev_error = campaign_doc.get("error") if campaign_doc.get("error_is_dev_level") else None

    accounts = []
    for cfg in configs:
        hit = (cfg.get("account_id") or "").removeprefix("act_") == err_acc
        node_doc = campaign_doc if (not split or hit) else None
        campaigns = []
        for c in cfg.get("campaigns") or []:
            adsets = []
            for a in c.get("adsets") or []:
                ads = [
                    {**_stage_node(ad.get("name"), None), "ad_id": None}
                    for ad in (a.get("ads") or [])
                ]
                promoted_object = a.get("promoted_object") or {}
                adsets.append(
                    {
                        **_stage_node(a.get("name"), None),
                        "custom_event_type": promoted_object.get("custom_event_type"),
                        "ads": ads,
                    }
                )
            camp_node = {**_stage_node(c.get("name"), node_doc), "adsets": adsets}
            if split and not hit:
                camp_node["_resolve_by_adset"] = True
                camp_node["_dev_error"] = dev_error
            campaigns.append(camp_node)
        accounts.append(
            {
                "account_id": cfg.get("account_id"),
                "account_name": cfg.get("account_name"),
                "game_platform": cfg.get("game_platform"),
                "campaigns": campaigns,
            }
        )
    return {
        "_id": campaign_doc["_id"],
        "batch_id": data.get("batch_id"),
        "start_time": campaign_doc.get("start_time"),
        "update_time": campaign_doc.get("update_time"),
        "mode": "full",
        "accounts": accounts,
        "data": {
            "type": OpType.CREATE.value,
            "batch_id": data.get("batch_id"),
            "real_name": (campaign_doc.get("data") or {}).get("real_name"),
        },
    }


def _index_full_item(item: dict) -> dict:
    """构建 (acc, c_name[, a_name[, ad_name]]) → 节点指针 的三层索引，O(1) 挂载。"""
    index = {"adset": {}, "ad": {}}
    for acc in item.get("accounts") or []:
        acc_id = acc.get("account_id")
        for c in acc.get("campaigns") or []:
            c_name = c.get("name")
            for a in c.get("adsets") or []:
                a_name = a.get("name")
                index["adset"][(acc_id, c_name, a_name)] = a
                for ad in a.get("ads") or []:
                    # 同名素材可能在一个组里出现多次，挂成列表统一回贴，避免后建的覆盖先建的
                    index["ad"].setdefault(
                        (acc_id, c_name, a_name, ad.get("name")), []
                    ).append(ad)
    return index


def _attach_doc_to_node(node: dict, doc: dict, status: str | None = None) -> None:
    node["status"] = status if status is not None else doc.get("status")
    node["error"] = doc.get("error")
    node["stage_id"] = doc["_id"]


def _attach_adset_doc(
    doc: dict,
    full_indexes: list[tuple[dict, dict]],
    adsets_with_downstream_ads: set[tuple[str | None, str, str]],
) -> bool:
    """把组 doc 的 status/error 挂到匹配的 adset 节点。

    老版本一条组消息可包含多个广告组：其中一个失败会让整条 doc=FAILED，但已
    成功的广告组必然已推送出下游广告消息。对此类节点按下游消息回填 COMPLETED，
    防止批次级错误扩散到兄弟系列；新版本每条组消息仅一个广告组，也兼容此规则。
    """
    data = doc.get("data") or {}
    matched = False
    for cfg in data.get("create_config") or []:
        key = (cfg.get("account_id"), cfg.get("campaign_name"), cfg.get("name"))
        for _item, index in full_indexes:
            node = index["adset"].get(key)
            if node is not None:
                if doc.get("status") == "FAILED" and key in adsets_with_downstream_ads:
                    node["status"] = "COMPLETED"
                    node["error"] = None
                    node["stage_id"] = doc["_id"]
                else:
                    _attach_doc_to_node(node, doc)
                matched = True
    return matched


def _collect_adsets_with_downstream_ads(
    ad_docs: list[dict],
) -> set[tuple[str | None, str, str]]:
    """已生成广告消息的广告组键，证明对应广告组创建已成功。"""
    result = set()
    for doc in ad_docs:
        for cfg in (doc.get("data") or {}).get("create_config") or []:
            parts = (cfg.get("adset_name") or "").split("||", 1)
            if len(parts) == 2:
                result.add((cfg.get("account_id"), parts[0], parts[1]))
    return result


def _resolve_ad_status(
    doc_status: str | None,
    account_id: str | None,
    adset_id: str | None,
    ad_name: str | None,
    task_map: dict,
) -> str | None:
    """FAILED 的广告 doc 按 ad_task hash 判定单条广告真实状态；其它状态沿用 doc 状态。

    hash 里出现该 ad_name(组建成功且这条广告也建成功)→ COMPLETED；否则 FAILED
    (hash 为空即组下广告都没建出来)。
    """
    if doc_status != "FAILED":
        return doc_status
    created = task_map.get((account_id, adset_id)) or {}
    return "COMPLETED" if ad_name in created else "FAILED"


def _attach_ad_doc(
    doc: dict, full_indexes: list[tuple[dict, dict]], task_map: dict
) -> bool:
    """把广告 doc 的 status/error 挂到 full item 的匹配 ad 节点；返回是否命中任一节点。

    广告 doc 中每个 create_config[i] 自身就是一个广告：cfg.name = ad_name，
    cfg.adset_name 形如 "campaign_name||adset_name"。doc 为 FAILED 时按 ad_task
    hash 拆分出每条广告的真实成败。
    """
    data = doc.get("data") or {}
    doc_status = doc.get("status")
    matched = False
    for cfg in data.get("create_config") or []:
        adset_name_full = cfg.get("adset_name") or ""
        parts = adset_name_full.split("||", 1)
        if len(parts) != 2:
            continue
        c_name, a_name = parts
        ad_name = cfg.get("name")
        key = (cfg.get("account_id"), c_name, a_name, ad_name)
        status = _resolve_ad_status(
            doc_status, cfg.get("account_id"), cfg.get("adset_id"), ad_name, task_map
        )
        for _item, index in full_indexes:
            for node in index["ad"].get(key) or ():
                _attach_doc_to_node(node, doc, status)
                matched = True
    return matched


def _build_ads_only_item(ad_doc: dict, task_map: dict) -> dict:
    """未匹配到系列骨架的广告 doc → 独立 mode=ads_only item，campaign/adset 层仅占位。

    广告 doc 中每个 create_config[i] 自身就是一个广告（cfg.name = ad_name）。doc 为
    FAILED 时按 ad_task hash 拆分出每条广告的真实成败：hash 存在=组建成功，按广告名
    匹配；hash 为空=组下广告全失败。
    """
    data = ad_doc.get("data") or {}
    doc_status = ad_doc.get("status")
    accounts_map: dict[str, dict] = {}
    for cfg in data.get("create_config") or []:
        acc_id = cfg.get("account_id")
        adset_id = cfg.get("adset_id")
        adset_name_full = cfg.get("adset_name") or ""
        parts = adset_name_full.split("||", 1)
        c_name = parts[0] if parts and parts[0] else ""
        a_name = parts[1] if len(parts) == 2 else ""
        acc_entry = accounts_map.setdefault(
            acc_id,
            {
                "account_id": acc_id,
                "account_name": cfg.get("account_name"),
                "game_platform": None,
                "_campaigns": {},
            },
        )
        camp = acc_entry["_campaigns"].setdefault(
            c_name, {**_stage_node(c_name, None), "_adsets": {}}
        )
        adset = camp["_adsets"].setdefault(
            a_name,
            {**_stage_node(a_name, None), "custom_event_type": None, "ads": []},
        )
        # 仅 doc 为 FAILED 时按 hash 还原组/广告真实状态；其它状态保持原占位行为
        if doc_status == "FAILED":
            camp["status"] = "COMPLETED"  # 让系列层进入按广告聚合分支
            adset["status"] = (
                "COMPLETED" if task_map.get((acc_id, adset_id)) else "FAILED"
            )
        ad_node = _stage_node(cfg.get("name"), ad_doc)
        ad_node["status"] = _resolve_ad_status(
            doc_status, acc_id, adset_id, cfg.get("name"), task_map
        )
        adset["ads"].append({**ad_node, "ad_id": None})

    accounts = []
    for acc_entry in accounts_map.values():
        campaigns = []
        for camp in acc_entry.pop("_campaigns").values():
            adsets = list(camp.pop("_adsets").values())
            camp["adsets"] = adsets
            campaigns.append(camp)
        acc_entry["campaigns"] = campaigns
        accounts.append(acc_entry)

    return {
        "_id": ad_doc["_id"],
        "batch_id": data.get("batch_id"),
        "start_time": ad_doc.get("start_time"),
        "update_time": ad_doc.get("update_time"),
        "mode": "ads_only",
        "accounts": accounts,
        "data": {
            "type": OpType.CREATE.value,
            "batch_id": data.get("batch_id"),
            "real_name": (ad_doc.get("data") or {}).get("real_name"),
        },
    }


def _resolve_marked_campaigns(item: dict) -> None:
    """回填失败批次里未命中 error 账户的系列:有组 doc(stage_id 已挂)→视为系列建成
    COMPLETED 走按组聚合;否则 FAILED,error 取 _dev_error(开发者级错误才有,账户级为空)。"""
    for acc in item.get("accounts") or []:
        for camp in acc.get("campaigns") or []:
            if not camp.pop("_resolve_by_adset", False):
                continue
            dev_error = camp.pop("_dev_error", None)
            if any(a.get("stage_id") is not None for a in camp.get("adsets") or []):
                camp["status"] = "COMPLETED"
            else:
                camp["status"] = "FAILED"
                camp["error"] = dev_error


def _merge_create_docs(
    campaign_docs: list[dict],
    adset_docs: list[dict],
    ad_docs: list[dict],
    task_map: dict,
) -> list[dict]:
    """编排 full 合并 + ads_only 兜底。"""
    full_items = [_build_full_item(d) for d in campaign_docs]
    full_indexes = [(item, _index_full_item(item)) for item in full_items]
    adsets_with_downstream_ads = _collect_adsets_with_downstream_ads(ad_docs)

    for doc in adset_docs:
        _attach_adset_doc(doc, full_indexes, adsets_with_downstream_ads)

    leftover_ad_docs = []
    for doc in ad_docs:
        if not _attach_ad_doc(doc, full_indexes, task_map):
            leftover_ad_docs.append(doc)

    for item in full_items:
        _resolve_marked_campaigns(item)

    ads_only_items = [_build_ads_only_item(d, task_map) for d in leftover_ad_docs]
    return full_items + ads_only_items


def _map_doc_status(doc_status) -> RowStatus:
    """worker 写入的 doc.status → 前端展示用的 RowStatus。"""
    if doc_status == "COMPLETED":
        return RowStatus.SUCCESS
    if doc_status == "FAILED":
        return RowStatus.FAILED
    if doc_status in (None, "PENDING"):
        return RowStatus.PENDING
    return RowStatus.STARTED


def _aggregate_campaign_status(campaign: dict) -> RowStatus:
    """聚合规则（系列 COMPLETED 后状态不再回退到 pending）：

    - 系列 FAILED → failed
    - 系列 PENDING/None → pending（任务还没启动）
    - 系列 STARTED/其它非 COMPLETED → started
    - 系列 COMPLETED：扫所有组和 ad
        - 任一组或 ad 未达终态 → started（即便 ad doc 还没出现也算在跑）
        - 全部终态：组 FAILED 视其下挂 ad 全失败，再按 ad 聚合 success/failed/partial
    """
    camp_status = campaign.get("status")
    if camp_status == "FAILED":
        return RowStatus.FAILED
    if camp_status != "COMPLETED":
        return _map_doc_status(camp_status)

    has_non_terminal = False
    ad_results: list[RowStatus] = []

    adsets = campaign.get("adsets") or []
    for adset in adsets:
        adset_status = adset.get("status")
        if adset_status == "FAILED":
            for _ad in adset.get("ads") or []:
                ad_results.append(RowStatus.FAILED)
            continue
        if adset_status != "COMPLETED":
            has_non_terminal = True
            continue
        # 组 COMPLETED → 检查其下 ad
        for ad in adset.get("ads") or []:
            ad_status = ad.get("status")
            if ad_status == "COMPLETED":
                ad_results.append(RowStatus.SUCCESS)
            elif ad_status == "FAILED":
                ad_results.append(RowStatus.FAILED)
            else:
                has_non_terminal = True

    if has_non_terminal:
        return RowStatus.STARTED

    statuses = set(ad_results)
    if statuses == {RowStatus.SUCCESS}:
        return RowStatus.SUCCESS
    if statuses == {RowStatus.FAILED}:
        return RowStatus.FAILED
    return RowStatus.PARTIAL


def _collect_custom_event_types(campaign: dict) -> str | None:
    events = {
        adset.get("custom_event_type")
        for adset in campaign.get("adsets") or []
        if adset.get("custom_event_type")
    }
    if not events:
        return None
    return ", ".join(sorted(events))


def _compute_create_stats(campaign: dict) -> dict:
    """按系列汇总组/广告的成功失败计数,并收集失败广告的素材名(去重)。

    口径与 _aggregate_campaign_status 一致:
      - 系列 FAILED / 组 FAILED → 该组下所有广告都算失败(广告 doc 可能还没建出来)
      - 组 COMPLETED → 按各 ad 实际 status 分桶
      - 其余非终态 → 计入 in_progress
    """
    camp_status = campaign.get("status")
    adsets = campaign.get("adsets") or []

    adset_total = len(adsets)
    adset_success = 0
    adset_failed = 0

    ad_total = 0
    ad_success = 0
    ad_failed = 0

    failed_ad_names: list[str] = []
    seen_failed: set[str] = set()

    def _record_failed(name: str | None) -> None:
        if name and name not in seen_failed:
            seen_failed.add(name)
            failed_ad_names.append(name)

    for adset in adsets:
        ads = adset.get("ads") or []
        ad_total += len(ads)
        adset_status = adset.get("status")

        if camp_status == "FAILED" or adset_status == "FAILED":
            adset_failed += 1
            for ad in ads:
                ad_failed += 1
                _record_failed(ad.get("name"))
            continue

        if adset_status == "COMPLETED":
            adset_success += 1
            for ad in ads:
                ad_status = ad.get("status")
                if ad_status == "COMPLETED":
                    ad_success += 1
                elif ad_status == "FAILED":
                    ad_failed += 1
                    _record_failed(ad.get("name"))

    return {
        "adset_stats": {
            "total": adset_total,
            "success": adset_success,
            "failed": adset_failed,
            "in_progress": adset_total - adset_success - adset_failed,
        },
        "ad_stats": {
            "total": ad_total,
            "success": ad_success,
            "failed": ad_failed,
            "in_progress": ad_total - ad_success - ad_failed,
        },
        "failed_ad_names": failed_ad_names,
    }


def _pick_first_error(campaign: dict) -> str | None:
    if campaign.get("error"):
        return f"创建系列报错: {campaign['error']}"
    for adset in campaign.get("adsets") or []:
        if adset.get("error"):
            return f"创建广告组报错: {adset['error']}"
        for ad in adset.get("ads") or []:
            if ad.get("error"):
                return f"创建广告报错: {ad['error']}"
    return None


def flatten_to_campaign_rows(items: list[dict]) -> list[dict]:
    """合并后的 create item → 户×系列 维度的汇总行。"""
    rows = []
    for item in items:
        for acc in item.get("accounts") or []:
            for campaign in acc.get("campaigns") or []:
                stats = _compute_create_stats(campaign)
                rows.append(
                    {
                        "_id": str(item["_id"]),
                        "batch_id": item.get("batch_id"),
                        "start_time": item.get("start_time"),
                        "game_platform": acc.get("game_platform"),
                        "account_id": acc.get("account_id"),
                        "account_name": acc.get("account_name"),
                        "campaign_name": campaign.get("name"),
                        "custom_event_type": _collect_custom_event_types(campaign),
                        "status": _aggregate_campaign_status(campaign),
                        "error": _pick_first_error(campaign),
                        "adset_stats": stats["adset_stats"],
                        "ad_stats": stats["ad_stats"],
                        "failed_ad_names": stats["failed_ad_names"],
                        "data": {
                            "type": OpType.CREATE.value,
                            "batch_id": item.get("batch_id"),
                            "real_name": (item.get("data") or {}).get("real_name"),
                        },
                    }
                )
    return rows


async def _load_ad_task_map(ad_docs: list[dict]) -> dict:
    """收集 FAILED 广告 doc 涉及的 (account_id, adset_id)，批量读 Redis ad_task hash。

    返回 {(account_id, adset_id): {ad_name: ad_id}}；hash 非空即代表广告组创建成功，
    其中的 ad_name 即创建成功的广告。只有 FAILED 才需要回查，其余状态无需 Redis。
    """
    pairs = set()
    for doc in ad_docs:
        if doc.get("status") != "FAILED":
            continue
        for cfg in (doc.get("data") or {}).get("create_config") or []:
            account_id = cfg.get("account_id")
            adset_id = cfg.get("adset_id")
            if account_id and adset_id:
                pairs.add((account_id, adset_id))
    if not pairs:
        return {}

    pairs = list(pairs)
    pipe = redis_cli_3.pipeline(transaction=False)
    for account_id, adset_id in pairs:
        pipe.hgetall(f"ad_task:{account_id}:{adset_id}")
    results = await pipe.execute()
    return {pair: (res or {}) for pair, res in zip(pairs, results)}


async def build_create_rows(
    campaign_docs: list[dict],
    adset_docs: list[dict],
    ad_docs: list[dict],
) -> list[dict]:
    """按 batch_id 隔离后，合并 create 三阶段 doc 并展开为户×系列汇总行。

    新创建任务的系列、广告组、广告分别是独立队列消息；同批次的消息通过 batch_id
    关联。旧记录没有 batch_id 时保留原有全量名称匹配逻辑，避免影响历史查询。
    """
    task_map = await _load_ad_task_map(ad_docs)
    batches: dict[str, dict[str, list[dict]]] = defaultdict(
        lambda: {"campaign": [], "adset": [], "ad": []}
    )

    def _append(stage: str, docs: list[dict]) -> None:
        for doc in docs:
            batch_id = (doc.get("data") or {}).get("batch_id")
            # 无 batch_id 的老数据继续共用 legacy 组，维持上线前的合并行为。
            key = f"batch:{batch_id}" if batch_id else "legacy"
            batches[key][stage].append(doc)

    _append("campaign", campaign_docs)
    _append("adset", adset_docs)
    _append("ad", ad_docs)

    items = []
    for docs in batches.values():
        items.extend(
            _merge_create_docs(
                docs["campaign"], docs["adset"], docs["ad"], task_map
            )
        )
    return flatten_to_campaign_rows(items)


def trim_operation_history_data(doc: dict) -> dict:
    """就地裁剪 ad_operations doc 的 data 字段为前端展示用的精简结构。"""
    data = doc.get("data") or {}
    raw_type = data.get("type")
    trimmed = {"type": raw_type, "real_name": data.get("real_name")}

    if raw_type in {
        OpType.BUDGET.value,
        OpType.PAUSE.value,
        OpType.START.value,
        OpType.DELETE.value,
    }:
        trimmed.update(
            {
                "level": data.get("level"),
                "id": data.get("id"),
                "name": (
                    (data.get("ext_info") or {}).get("name")
                    if isinstance(data.get("ext_info"), dict)
                    else None
                ),
                "value": (
                    data.get("value") / 100 if data.get("value") is not None else None
                ),
            }
        )
    elif raw_type == OpType.CREATE.value:
        trimmed["create_config"] = data.get("create_config", [])

    doc["data"] = trimmed
    return doc
