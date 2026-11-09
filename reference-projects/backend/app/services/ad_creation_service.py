import copy
import json
import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from app.db.clients import redis_cli_3
from app.db.op_queue import push_op_message
from app.db.mongo import cols
from app.model_type_defs.ad_operation import OperationFields, OpType
from app.model_type_defs.user_models import UserModel
from app.utils.message_signing import OP_API_KEY, sign_payload

CREATIVE_HISTORY_LIMIT = 100

creative_histories_collection = cols.creative_histories


async def cleanup_creative_histories(username: str):
    count = await creative_histories_collection.count_documents({"username": username})

    if count <= CREATIVE_HISTORY_LIMIT:
        return

    cursor = (
        creative_histories_collection.find({"username": username})
        .sort("created_at", -1)
        .skip(CREATIVE_HISTORY_LIMIT)
    )
    ids_to_delete = []
    async for doc in cursor:
        ids_to_delete.append(doc["_id"])

    if ids_to_delete:
        await creative_histories_collection.delete_many({"_id": {"$in": ids_to_delete}})


async def save_creative_history(ads: list[dict], current_user: UserModel):
    if not ads:
        return

    try:
        creatives = []
        for ad in ads:
            creative = ad.get("creative") or {}
            creatives.append(
                {
                    "type": creative.get("type"),
                    "image_hash": creative.get("image_hash"),
                    "video_id": creative.get("video_id"),
                    "path": creative.get("path"),
                    "picture": creative.get("picture"),
                    "title": creative.get("title"),
                    "body": creative.get("body"),
                    "description": creative.get("description"),
                    "call_to_action": creative.get("call_to_action"),
                    "page_welcome_message": creative.get("page_welcome_message"),
                    "basename": creative.get("basename"),
                    "img": creative.get("img"),
                }
            )

        china_tz = timezone(timedelta(hours=8))
        now = datetime.now(timezone.utc).astimezone(china_tz)
        history_doc = {
            "username": current_user.username,
            "real_name": current_user.real_name,
            "creatives": creatives,
            "creatives_count": len(creatives),
            "created_at": now.isoformat(),
        }

        await creative_histories_collection.insert_one(history_doc)
        await cleanup_creative_histories(current_user.username)
    except Exception as exc:
        logging.error(f"保存素材创意历史失败: {exc}")


def _expand_account_groups(account_groups: list[dict]) -> list[dict]:
    all_accounts = []
    for group in account_groups:
        for account in group.get("account_ids", []):
            account_info = copy.deepcopy(account)
            account_info["game_platform"] = group["game_platform"]
            account_info["country"] = group["country"]
            account_info["agent_line"] = group["agent_line"]
            account_info["link_url"] = group["link_url"]
            all_accounts.append(account_info)
    return all_accounts


# 只在分配阶段使用、不发给下游的字段
_ALLOC_ONLY_FIELDS = (
    "target_account_name",
    "target_adset_name",
    "material_tags",
    "by_tag",
)


def _strip_alloc_fields(ad: dict) -> dict:
    for f in _ALLOC_ONLY_FIELDS:
        ad.pop(f, None)
    return ad


async def attach_material_tags(ads: list[dict]) -> None:
    """按 creative.basename 查 materials.tags_new,挂到 ad['material_tags']。"""
    basenames = {
        basename
        for ad in ads
        if (basename := (ad.get("creative") or {}).get("basename"))
    }
    tag_map: dict = {}
    if basenames:
        async for doc in cols.materials.find(
            {"basename": {"$in": list(basenames)}},
            {"basename": 1, "tags_new": 1},
        ):
            tag_map[doc["basename"]] = doc.get("tags_new") or []
    for ad in ads:
        basename = (ad.get("creative") or {}).get("basename")
        ad["material_tags"] = tag_map.get(basename) or []


def _tag_conflict(a: set, b: set) -> bool:
    """标签集互相包含(含相等)视为同质素材,不允许同组;无标签的不参与约束。"""
    return bool(a) and bool(b) and (a <= b or b <= a)


def _pool_dynamic_ads(ads: list[dict]) -> list[dict]:
    """同类型素材池化成 1 条动态广告,挂在 ad['dynamic_members']。
    FB 动态组只能 1 条广告且只能一种格式,故图片/视频混选或含引用原贴会产出多条 → 报错。"""
    seen: set = set()
    groups: dict = {}
    passthrough: list[dict] = []
    for ad in ads:
        name = ad.get("name")
        if name in seen:
            continue
        seen.add(name)
        creative = ad.get("creative") or {}
        if creative.get("post_id"):
            passthrough.append(ad)
            continue
        groups.setdefault(creative.get("type"), []).append(ad)

    result: list[dict] = []
    for members in groups.values():
        if len(members) == 1:
            result.append(members[0])
            continue
        pooled = copy.deepcopy(members[0])
        pooled["dynamic_members"] = [
            {"name": m.get("name"), "creative": m.get("creative") or {}}
            for m in members
        ]
        result.append(pooled)
    result.extend(passthrough)
    # FB 动态素材广告组只能有 1 条广告;图片/视频混选或含引用原贴会产出多条 → 拦截
    if len(result) > 1:
        raise ValueError(
            "动态素材广告组只能有 1 条广告,但该组素材类型不一致"
            "(图片/视频混选或含引用原贴),请拆到不同广告组。"
        )
    return result


def _allocate_ads_to_slots(
    all_accounts: list[dict], original_ads: list[dict], ad_num: int,
    by_tag: bool = False,
) -> None:
    """把 ads 填进已构建好的 account → campaigns → adsets 骨架。

    Phase 1:带 target_account_name / target_adset_name 的 ad 走精确投放,在
            (account_name × adset.name) 匹配的位置各塞一份,不消耗 ad_num 名额。
    Phase 2:剩下未指定的 ad 走全局均分,补齐每个 adset 到 ad_num;若某 adset
            因指定已 ≥ ad_num,不再补也不删,允许超员。by_tag 时额外要求候选素材
            标签集与组内已有素材互不包含,凑不齐再放宽。
    Phase 3:动态素材组(is_dynamic_creative)把自己在 Phase 1/2 分到的素材合并成 1 条
            动态广告(图片/视频不能混,混了会报错)。
    """
    for account in all_accounts:
        for campaign in account.get("campaigns") or []:
            for adset in campaign.get("adsets") or []:
                adset["ads"] = []

    if not original_ads or not all_accounts:
        return

    pinned_ads: list[dict] = []
    random_ads: list[dict] = []
    for ad in original_ads:
        if ad.get("target_account_name") or ad.get("target_adset_name"):
            pinned_ads.append(ad)
        else:
            random_ads.append(ad)

    for ad in pinned_ads:
        target_account = ad.get("target_account_name")
        target_adset = ad.get("target_adset_name")
        target_campaign_name: str | None = None
        target_adset_name: str | None = None
        if target_adset:
            if "/" in target_adset:
                target_campaign_name, target_adset_name = target_adset.split("/", 1)
            else:
                target_adset_name = target_adset
        placed = False
        for account in all_accounts:
            if target_account and account.get("account_name") != target_account:
                continue
            for campaign in account.get("campaigns") or []:
                if target_campaign_name and campaign.get("name") != target_campaign_name:
                    continue
                matched_adsets = [
                    adset
                    for adset in campaign.get("adsets") or []
                    if not target_adset_name or adset.get("name") == target_adset_name
                ]
                if not matched_adsets:
                    continue
                # 没指定具体组时,同一系列下只随机挑一个,避免一个广告在多组里重复出现
                chosen = matched_adsets if target_adset_name else [random.choice(matched_adsets)]
                for adset in chosen:
                    ad_copy = _strip_alloc_fields(copy.deepcopy(ad))
                    ad_copy["link_url"] = account.get("link_url")
                    adset["ads"].append(ad_copy)
                    placed = True
        if not placed:
            logging.warning(
                f"指定广告未匹配任何投放位置,已跳过: name={ad.get('name')}, "
                f"target_account_name={target_account!r}, "
                f"target_adset_name={target_adset!r}"
            )

    # Phase 2:所有组(含动态组)按 ad_num 全局均分,素材在组间分散
    if random_ads:
        slots: list[tuple[dict, dict, int]] = []
        for account in all_accounts:
            for campaign in account.get("campaigns") or []:
                for adset in campaign.get("adsets") or []:
                    deficit = ad_num - len(adset["ads"])
                    if deficit > 0:
                        slots.append((adset, account, deficit))

        total_slots = sum(s[2] for s in slots)
        if total_slots > 0:
            random_count = len(random_ads)
            base = total_slots // random_count
            remainder = total_slots % random_count
            remaining_counts = {i: base for i in range(random_count)}
            if remainder > 0:
                for idx in random.sample(range(random_count), remainder):
                    remaining_counts[idx] += 1

            tag_sets = [set(ad.get("material_tags") or []) for ad in random_ads]
            tags_by_name = {
                ad["name"]: set(ad.get("material_tags") or []) for ad in original_ads
            }

            for adset, account, deficit in slots:
                link_url = account.get("link_url")
                used_names = {a.get("name") for a in adset["ads"]}
                adset_tags = [
                    tags_by_name.get(a.get("name"), set()) for a in adset["ads"]
                ]
                for _ in range(deficit):
                    pool = [
                        i
                        for i in range(random_count)
                        if remaining_counts[i] > 0
                        and random_ads[i]["name"] not in used_names
                    ]
                    candidates = pool
                    if by_tag:
                        def _tag_ok(i):
                            return not any(
                                _tag_conflict(tag_sets[i], t) for t in adset_tags
                            )

                        candidates = [i for i in pool if _tag_ok(i)]
                        if not candidates:
                            # 标签约束优先于配额均分,允许配额透支
                            candidates = [
                                i
                                for i in range(random_count)
                                if random_ads[i]["name"] not in used_names
                                and _tag_ok(i)
                            ]
                        if pool and not candidates:
                            logging.warning(
                                f"标签分组无兼容素材,放宽标签约束: adset={adset.get('name')}"
                            )
                            candidates = pool
                    if not candidates:
                        candidates = [
                            i for i in range(random_count) if remaining_counts[i] > 0
                        ]
                    if not candidates:
                        candidates = list(range(random_count))

                    max_remaining = max(remaining_counts[i] for i in candidates)
                    best = [i for i in candidates if remaining_counts[i] == max_remaining]
                    chosen = random.choice(best)

                    remaining_counts[chosen] -= 1
                    used_names.add(random_ads[chosen]["name"])
                    adset_tags.append(tag_sets[chosen])
                    ad_copy = _strip_alloc_fields(copy.deepcopy(random_ads[chosen]))
                    ad_copy["link_url"] = link_url
                    adset["ads"].append(ad_copy)

    # Phase 3:动态素材组把自己分到的那 ad_num 个素材按类型合并成 1 条动态广告
    for account in all_accounts:
        for campaign in account.get("campaigns") or []:
            for adset in campaign.get("adsets") or []:
                if adset.get("is_dynamic_creative"):
                    adset["ads"] = _pool_dynamic_ads(adset["ads"])


def distribute_ads(config: dict) -> dict:
    ad_num = config.get("ad_num", 1)
    original_ads = config.pop("ads", [])
    by_tag = any(ad.get("by_tag") for ad in original_ads)
    template_campaigns = config.pop("campaigns", [])
    all_accounts = _expand_account_groups(config.pop("account_groups", []))

    for account in all_accounts:
        account["campaigns"] = copy.deepcopy(template_campaigns)

    _allocate_ads_to_slots(all_accounts, original_ads, ad_num, by_tag)

    config["accounts"] = all_accounts
    return config


def distribute_ads_for_app_promotion(config: dict) -> dict:
    """OUTCOME_APP_PROMOTION 专用分配策略。

    按 campaign 第一个 adset 的 promoted_object.object_store_url 去 account_groups
    里找 link_url 相同的 group;该 campaign 只在该 group 内的账户上生成(每户一份
    deepcopy),不再笛卡尔到全部账户。ads 填充逻辑与 distribute_ads 共用。
    """
    ad_num = config.get("ad_num", 1)
    original_ads = config.pop("ads", [])
    by_tag = any(ad.get("by_tag") for ad in original_ads)
    template_campaigns = config.pop("campaigns", [])
    account_groups = config.pop("account_groups", [])

    groups_by_url = {g["link_url"]: g for g in account_groups if g.get("link_url")}

    accounts_map: dict[str, dict] = {}
    for campaign in template_campaigns:
        adsets = campaign.get("adsets") or []
        if not adsets:
            continue
        url = (adsets[0].get("promoted_object") or {}).get("object_store_url")
        group = groups_by_url.get(url)
        if not group:
            logging.warning(
                f"OUTCOME_APP_PROMOTION 系列未匹配到 link_url 相同的 group: "
                f"object_store_url={url}, campaign={campaign.get('name')}"
            )
            continue
        for raw_account in group.get("account_ids") or []:
            acc_id = raw_account["account_id"]
            account_info = accounts_map.get(acc_id)
            if account_info is None:
                account_info = copy.deepcopy(raw_account)
                account_info["game_platform"] = group["game_platform"]
                account_info["country"] = group["country"]
                account_info["agent_line"] = group["agent_line"]
                account_info["link_url"] = group["link_url"]
                account_info["campaigns"] = []
                accounts_map[acc_id] = account_info
            account_info["campaigns"].append(copy.deepcopy(campaign))

    all_accounts = list(accounts_map.values())
    _allocate_ads_to_slots(all_accounts, original_ads, ad_num, by_tag)

    config["accounts"] = all_accounts
    return config


async def _get_dev_app(account_id: str, page_id: str) -> dict:
    """根据广告账户ID和主页ID查找开发者应用凭据"""
    sys_user = await cols.fb_system_users.find_one(
        {
            "accounts.id": account_id.removeprefix("act_"),
            "pages.id": page_id,
        },
        {"_id": 1},
    )
    if not sys_user:
        raise ValueError(
            f"未找到绑定该广告账户和主页的系统开发者: {account_id}（主页{page_id}）"
        )
    dev_info = await cols.accounts.find_one(
        {"app_id": sys_user["_id"], "status": 1},
        {"app_id": 1, "access_token": 1, "_id": 0, "app_secret": 1, "proxy": 1},
    )
    if not dev_info:
        raise ValueError(
            f"未找到有效开发者配置: {account_id}（主页{page_id}）"
        )
    return dev_info


async def _resolve_dev_app(object_type: str, person_id: str) -> dict:
    """根据 choose_dev 返回的 type + id 解析开发者凭据"""
    if object_type == "personal":
        personal_account = await cols.personal_accounts.find_one(
            {"_id": person_id, "status": True},
            {"app_id": 1, "access_token": 1},
        )
        if not personal_account:
            raise ValueError("没有授权个号，请使用系统开发者")
        dev_config = await cols.accounts.find_one(
            {"app_id": personal_account["app_id"], "status": 1},
            {"app_id": 1, "app_secret": 1, "proxy": 1},
        )
        if not dev_config:
            raise ValueError("未找到个号对应的开发者配置，请使用系统开发者")
        return {
            "app_id": dev_config["app_id"],
            "access_token": personal_account["access_token"],
            "app_secret": dev_config["app_secret"],
            "proxy": dev_config.get("proxy"),
        }
    else:
        dev_app = await cols.accounts.find_one(
            {"_id": ObjectId(person_id), "status": 1},
            {"_id": 0, "app_id": 1, "access_token": 1, "app_secret": 1, "proxy": 1},
        )
        if not dev_app:
            raise ValueError("未找到有效的系统开发者配置")
        return dev_app

async def create_adset_ads(request_data: dict, current_user: UserModel):
    """批量在已有广告组下创建广告，每个 ad config 带 adset_id 直接走 _flow_ad"""
    account_id = request_data["account_id"]
    page_id = request_data["page_id"]
    link_url = request_data["link_url"]
    object_type = request_data["object_type"]
    personal_id = request_data["personal_id"]
    if object_type and personal_id:
        dev_app = await _resolve_dev_app(object_type, personal_id)
    else:
        dev_app = await _get_dev_app(account_id, page_id)
    create_config = []
    for op in request_data.get("operations", []):
        adset_id = op["adset_id"]
        campaign_name = op.get("campaign_name") or ""
        adset_name = op.get("adset_name") or adset_id
        full_adset_name = f"{campaign_name}||{adset_name}"
        op_page_id = op.get("page_id") or page_id

        for ad in op.get("ads", []):
            ad_cfg = copy.deepcopy(ad)
            ad_cfg["adset_id"] = adset_id
            ad_cfg["adset_name"] = full_adset_name
            ad_cfg["account_id"] = account_id
            ad_cfg["page_id"] = op_page_id
            ad_cfg["link_url"] = link_url
            create_config.append(ad_cfg)

    if not create_config:
        return

    create_message: OperationFields = {
        "type": OpType.CREATE,
        "dev_app": dev_app,
        "auto_run": True,
        "is_send": False,
        "create_config": create_config,
        "batch_id": uuid.uuid4().hex,
        "real_name": current_user.real_name,
        "user_id": current_user.id,
    }
    china_tz = timezone(timedelta(hours=8))
    now = datetime.now(timezone.utc).astimezone(china_tz)
    insert_result = await cols.ad_operations.insert_one(
        {"status": "PENDING", "start_time": now, "data": create_message}
    )
    create_message["_id"] = str(insert_result.inserted_id)
    signed_message = sign_payload(create_message, OP_API_KEY)
    msg = json.dumps(signed_message, ensure_ascii=False).encode("utf-8")
    await push_op_message(create_message, msg)
    logging.info(f"create_adset_ads 创建任务已提交, 广告数: {len(create_config)}")


async def delete_adset_ads(request_data: dict, current_user: UserModel):
    """批量删除广告"""
    ads = request_data.get("ads", [])
    object_type = request_data["object_type"]
    personal_id = request_data["personal_id"]
    dev_app = None
    if object_type and personal_id:
        dev_app = await _resolve_dev_app(object_type, personal_id)
    china_tz = timezone(timedelta(hours=8))
    now = datetime.now(timezone.utc).astimezone(china_tz)
    for ad in ads:
        delete_message: OperationFields = {
            "type": OpType.DELETE,
            "dev_app": dev_app,
            "auto_run": True,
            "is_send": True,
            "level": "ad",
            "id": ad["id"],
            "real_name": current_user.real_name,
            "user_id": current_user.id,
        }
        insert_result = await cols.ad_operations.insert_one(
            {"status": "PENDING", "start_time": now, "data": delete_message}
        )
        delete_message["_id"] = str(insert_result.inserted_id)
        signed_message = sign_payload(delete_message, OP_API_KEY)
        msg = json.dumps(signed_message, ensure_ascii=False).encode("utf-8")
        await push_op_message(delete_message, msg)

    logging.info(f"delete_adset_ads 删除任务已提交, 广告数: {len(ads)}")
