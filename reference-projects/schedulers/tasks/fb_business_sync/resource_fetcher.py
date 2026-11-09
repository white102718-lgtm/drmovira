# -*- coding:utf-8 -*-
"""
Facebook API 资源拉取器 - 使用分页 API 批量拉取资源

模块级函数，无类依赖。
"""

import logging
from typing import Callable
from collections import defaultdict

from facebook_business.api import FacebookSession, FacebookAdsApi
from facebook_business.adobjects.business import Business
from facebook_business.adobjects.user import User
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adspixel import AdsPixel
from facebook_business.adobjects.page import Page
from facebook_business.exceptions import FacebookRequestError

from conf.api_conf import get_proxies
from db.clients import mongo_client, redis_cli_2
from utils.common_util import handle_error, fb_api_retry
from tasks.fb_business_sync.db_writer import (
    upsert_account,
    upsert_page,
    upsert_pixel,
    upsert_business,
    upsert_business_,
    upsert_personal_account,
    upsert_account_pixel,
    merge_account_pixels,
)
from model_type_defs.fb_asset_type import FbSyncMessage, SyncFlags, SyncTargets

FB_API_PAGE_LIMIT = 50

ACCOUNT_FIELDS = [
    "name",
    "account_id",
    "account_status",
    "disable_reason",
    "currency",
    "amount_spent",
    "balance",
    "created_time",
    "timezone_name",
    "age",
    "end_advertiser",
    "funding_source_details",
    "is_prepay_account",
    "spend_cap",
    # "owner",
    "tax_id_status",
]

BM_ACCOUNT_FIELDS = [
    "name",
    "account_id",
    "account_status",
    "disable_reason",
    "currency",
    "amount_spent",
    "balance",
    "created_time",
    "timezone_name",
    "age",
    "funding_source_details",
    "is_prepay_account",
    "spend_cap",
    "tax_id_status",
]

PAGE_FIELDS = [
    "name",
    "id",
    # "is_published",
    "username",
    # "verification_status",
    # "link",
    # "fan_count",
    # "category",
    # "followers_count",
    # "talking_about_count",
    # "is_unclaimed",
    # "can_post",
    # "new_like_count",
    "picture{url,width,height}",
]

PIXEL_FIELDS = [
    "name",
    "id",
    "last_fired_time",
    "data_use_setting",
    "is_unavailable",
]


def _sync_key(doc_id: str) -> str:
    return f"fb:bm:sync:{doc_id}"


def _sync_processed_to_redis(doc_id: str, processed: str, total: str):
    redis_cli_2.set(_sync_key(doc_id), f"{processed}/{total}", xx=True, keepttl=True)


def _load_page_instagram_user_ids(page_ids: list[str]) -> dict:
    return {
        page["_id"]: page["instagram_user_id"]
        for page in mongo_client["fb_pages"].find(
            {"_id": {"$in": page_ids}},
            {"instagram_user_id": 1},
        )
        if page.get("instagram_user_id")
    }


@fb_api_retry
def _fetch_page_instagram_user_id(
    page_id: str,
    page_token: str,
    app_id: str,
    app_secret: str,
    proxy: str | None = None,
) -> str | None:
    session = FacebookSession(
        app_id,
        app_secret,
        page_token,
        proxies=get_proxies(proxy),
        timeout=(10, 30),
    )
    api = FacebookAdsApi(session)
    try:
        page = Page(page_id, api=api).api_get(
            params={"fields": "page_backed_instagram_accounts"}
        )
    except FacebookRequestError as e:
        logging.warning(
            f"page {page_id} 拉 instagram_user_id 失败，跳过：{e.api_error_message()}"
        )
        return None
    accounts = page.export_all_data().get("page_backed_instagram_accounts", {}).get(
        "data", []
    )
    return accounts[0].get("id") if accounts else None


@fb_api_retry
def _fetch_edge_page(
    edge_getter: Callable,
    fields: list[str],
    after: str | None = None,
    limit: int = FB_API_PAGE_LIMIT,
    params: dict | None = None,
):
    params = dict(params or {})
    params["limit"] = limit
    params["summary"] = False  # 关闭 SDK 默认每页请求的 total_count 汇总
    if after:
        params["after"] = after

    cursor = edge_getter(fields=fields, params=params)
    items = list(getattr(cursor, "_queue", []))
    has_next = not getattr(cursor, "_finished_iteration", True)
    next_after = cursor.params.get("after") if has_next else None
    return items, next_after, has_next


def _drain_edge_pages(
    edge_getter: Callable,
    fields: list[str],
    edge_label: str,
    on_item: Callable,
    limit: int = FB_API_PAGE_LIMIT,
    params: dict | None = None,
):
    after = None
    page_no = 1
    total = 0

    while True:
        items, next_after, has_next = _fetch_edge_page(
            edge_getter=edge_getter,
            fields=fields,
            after=after,
            limit=limit,
            params=params,
        )

        for item in items:
            on_item(item)

        total += len(items)
        logging.debug(
            f"{edge_label} 第{page_no}页拉取完成，本页{len(items)}条，累计{total}条"
        )

        if not has_next:
            return total
        if not next_after:
            logging.warning(
                f"{edge_label} 检测到下一页标记但缺少 after 游标，停止继续翻页"
            )
            return total

        after = next_after
        page_no += 1



@handle_error(error_message="拉取User资源失败")
def fetch_user_resources(message: FbSyncMessage, collected: dict):
    """拉取个人号的所有资源（Accounts + Pages + Pixels）并写入 MongoDB。

    accounts 只收集到 collected，由最外层一次性写入 personal_accounts；pages 仍在此写入。
    """
    doc_id = message["_id"]
    token_type = message.get("token_type")
    me = User(fbid="me")
    all_accounts = []
    all_pages = []
    all_pixels = []
    pixels_by_ac = defaultdict(list)

    logging.info(f"[User] 拉取 {doc_id} 的所有资源")

    # ── Accounts ──
    def _collect_account(account):
        all_accounts.append(account)
        upsert_account(dict(account))

    _drain_edge_pages(
        edge_getter=me.get_ad_accounts,
        fields=ACCOUNT_FIELDS,
        edge_label=f"[User {doc_id}] accounts",
        on_item=_collect_account,
    )
    collected["accounts"].extend(
        {"id": a.get("account_id"), "name": a.get("name")} for a in all_accounts
    )
    logging.info(f"[User {doc_id}] accounts: {len(all_accounts)}")
    # 分批打印账户详情，每50个一条日志
    for i in range(0, len(all_accounts), 50):
        batch = all_accounts[i:i + 50]
        ids = [a.get("account_id") for a in batch]
        logging.info(f"[User {doc_id}] accounts [{i+1}-{i+len(batch)}]: {ids}")

    # ── Pages ──
    def _collect_page(page):
        all_pages.append(dict(page))

    _drain_edge_pages(
        edge_getter=me.get_accounts,
        fields=PAGE_FIELDS + ["access_token"],
        edge_label=f"[User {doc_id}] pages",
        on_item=_collect_page,
    )
    if all_pages:
        page_instagram_user_ids = _load_page_instagram_user_ids(
            [p.get("id") for p in all_pages]
        )
        for page in all_pages:
            page_id = page.get("id")
            page["instagram_user_id"] = page_instagram_user_ids.get(
                page_id
            ) or _fetch_page_instagram_user_id(
                page_id,
                page.get("access_token"),
                message["app_id"],
                message["app_secret"],
                message.get("proxy"),
            )
            upsert_page(page)

        upsert_personal_account(
            {
                "_id": doc_id,
                "token_type": token_type,
                "data_type": "pages",
                "data": [
                    {"id": p.get("id"), "name": p.get("name")}
                    for p in all_pages
                ],
            }
        )
    logging.info(f"[User {doc_id}] pages: {len(all_pages)}")

    # ── Pixels（per account）──
    sync_flags = SyncFlags(**(message.get("sync_flags") or {}))
    if sync_flags.sync_pixels:
        for idx, account in enumerate(all_accounts, start=1):
            account_id = account.get("id")
            ac_id = account.get("account_id")
            if not account_id:
                continue

            account_obj = AdAccount(account_id)

            def _collect_pixel(pixel, _ac_id=ac_id):
                pixels_by_ac[_ac_id].append(
                    {"id": pixel.get("id"), "name": pixel.get("name")}
                )
                all_pixels.append(pixel)
                upsert_pixel(dict(pixel))

            _drain_edge_pages(
                edge_getter=account_obj.get_ads_pixels,
                fields=PIXEL_FIELDS,
                edge_label=f"[User {doc_id}] account {ac_id} pixels",
                on_item=_collect_pixel,
            )
            _sync_processed_to_redis(doc_id, str(idx), str(len(all_accounts)))

        logging.info(f"[User {doc_id}] pixels: {len(all_pixels)}")

        for account_id, pixel_list in pixels_by_ac.items():
            upsert_account_pixel({"account_id": account_id, "data": pixel_list})
    else:
        logging.info(f"[User {doc_id}] sync_pixels=False，跳过 Pixels 同步")

    logging.info(
        f"[User {doc_id}] 资源拉取完成: "
        f"{len(all_accounts)} Accounts, {len(all_pages)} Pages, {len(all_pixels)} Pixels"
    )


@fb_api_retry
def _api_get(obj, fields: list[str]):
    return obj.api_get(fields=fields)


@handle_error(error_message="定向拉取资源失败")
def fetch_targeted_resources(message: FbSyncMessage, targets: SyncTargets):
    """只拉 targets 指定的户/像素/主页,逐对象 upsert。

    不回写 personal_accounts / fb_businesses 的列表字段(那些是全量覆盖语义),
    指定像素是部分集合,合并进户的 pixels 而非覆盖。单个资产失败不中断批次。
    """
    doc_id = message["_id"]
    account_specs = targets.get("accounts") or []
    page_ids = targets.get("page_ids") or []
    total = len(account_specs) + len(page_ids)
    done = 0
    failed = []

    for spec in account_specs:
        ac_id = str(spec["account_id"]).removeprefix("act_").strip()
        pixel_ids = spec.get("pixel_ids") or []
        try:
            account = _api_get(AdAccount(f"act_{ac_id}"), ACCOUNT_FIELDS)
            upsert_account(dict(account))
        except FacebookRequestError as e:
            failed.append(f"act_{ac_id}: {e.api_error_message()}")
            done += 1
            _sync_processed_to_redis(doc_id, str(done), str(total))
            continue

        merged = []
        for pixel_id in pixel_ids:
            try:
                pixel = _api_get(AdsPixel(pixel_id), PIXEL_FIELDS)
                upsert_pixel(dict(pixel))
                merged.append({"id": pixel.get("id"), "name": pixel.get("name")})
            except FacebookRequestError as e:
                failed.append(f"pixel {pixel_id}: {e.api_error_message()}")
        if merged:
            merge_account_pixels({"account_id": ac_id, "data": merged})
        done += 1
        _sync_processed_to_redis(doc_id, str(done), str(total))

    if page_ids:
        cached_ig = _load_page_instagram_user_ids(page_ids)
        for page_id in page_ids:
            try:
                page = dict(_api_get(Page(page_id), PAGE_FIELDS + ["access_token"]))
                page["instagram_user_id"] = cached_ig.get(
                    page_id
                ) or _fetch_page_instagram_user_id(
                    page_id,
                    page.get("access_token"),
                    message["app_id"],
                    message["app_secret"],
                    message.get("proxy"),
                )
                upsert_page(page)
            except FacebookRequestError as e:
                failed.append(f"page {page_id}: {e.api_error_message()}")
            done += 1
            _sync_processed_to_redis(doc_id, str(done), str(total))

    logging.info(
        f"[{doc_id}] 定向拉取完成: {len(account_specs)} 户 {len(page_ids)} 主页, "
        f"失败 {len(failed)} 条"
    )
    for line in failed:
        logging.warning(f"[{doc_id}] 定向拉取失败: {line}")


def _fetch_bm_resources(business_id: str, collected: dict):
    """拉取单个 Business 下的 Accounts / Pages / Pixels 并写入 MongoDB。

    accounts 只收集到 collected，由最外层一次性写入 personal_accounts。
    """
    business_obj = Business(business_id)

    all_accounts = []
    all_pages = []
    all_pixels = []

    # ── Accounts（client + owned）──
    def _collect_account(account):
        all_accounts.append(account)
        upsert_account(dict(account))

    _drain_edge_pages(
        edge_getter=business_obj.get_client_ad_accounts,
        fields=BM_ACCOUNT_FIELDS,
        edge_label=f"[BM {business_id}] client accounts",
        on_item=_collect_account,
    )
    _drain_edge_pages(
        edge_getter=business_obj.get_owned_ad_accounts,
        fields=BM_ACCOUNT_FIELDS,
        edge_label=f"[BM {business_id}] owned accounts",
        on_item=_collect_account,
    )
    upsert_business_(
        {
            "business_id": business_id,
            "data_type": "accounts",
            "data": [
                {"id": a.get("account_id"), "name": a.get("name")}
                for a in all_accounts
            ],
        }
    )
    collected["accounts"].extend(
        {"id": a.get("account_id"), "name": a.get("name")} for a in all_accounts
    )
    logging.info(f"[BM {business_id}] accounts: {len(all_accounts)}")

    # ── Pages（client + owned）──
    def _collect_page(page):
        all_pages.append(page)
        upsert_page(dict(page))

    _drain_edge_pages(
        edge_getter=business_obj.get_client_pages,
        fields=PAGE_FIELDS,
        edge_label=f"[BM {business_id}] client pages",
        on_item=_collect_page,
    )
    _drain_edge_pages(
        edge_getter=business_obj.get_owned_pages,
        fields=PAGE_FIELDS,
        edge_label=f"[BM {business_id}] owned pages",
        on_item=_collect_page,
    )
    upsert_business_(
        {
            "business_id": business_id,
            "data_type": "pages",
            "data": [
                {"id": p.get("id"), "name": p.get("name")}
                for p in all_pages
            ],
        }
    )
    logging.info(f"[BM {business_id}] pages: {len(all_pages)}")

    # ── Pixels（client + ads）──
    def _collect_pixel(pixel):
        all_pixels.append(pixel)
        upsert_pixel(dict(pixel))

    _drain_edge_pages(
        edge_getter=business_obj.get_client_pixels,
        fields=PIXEL_FIELDS,
        edge_label=f"[BM {business_id}] client pixels",
        on_item=_collect_pixel,
        # client_pixels 数据量大, limit=50 会触发 FB code1 "reduce the amount of data"
        limit=10,
    )
    _drain_edge_pages(
        edge_getter=business_obj.get_ads_pixels,
        fields=PIXEL_FIELDS,
        edge_label=f"[BM {business_id}] ads pixels",
        on_item=_collect_pixel,
    )
    upsert_business_(
        {
            "business_id": business_id,
            "data_type": "pixels",
            "data": [
                {"id": p.get("id"), "name": p.get("name")}
                for p in all_pixels
            ],
        }
    )
    logging.info(
        f"[BM {business_id}] 资源拉取完成: "
        f"{len(all_accounts)} Accounts, {len(all_pages)} Pages, {len(all_pixels)} Pixels"
    )


@handle_error(error_message="拉取BM资源失败")
def fetch_bm_all(message: FbSyncMessage, collected: dict):
    """获取用户的所有 Business 列表，然后逐个拉取资源。"""
    doc_id = message["_id"]
    token_type = message.get("token_type")
    me = User(fbid="me")
    businesses = [
        {"business_id": b.get("id"), "business_name": b.get("name")}
        for b in me.get_businesses(fields=["id", "name"])
    ]

    if not businesses:
        logging.info(f"[{token_type} {doc_id}] 没有 Business")
        return

    logging.info(f"[{token_type} {doc_id}] 找到 {len(businesses)} 个 Business")

    # 写入 personal_accounts / fb_system_users
    upsert_personal_account(
        {
            "_id": doc_id,
            "token_type": token_type,
            "data_type": "business",
            "data": [
                {"id": biz["business_id"], "name": biz["business_name"]}
                for biz in businesses
            ],
        }
    )

    # 写入 fb_businesses
    for biz in businesses:
        upsert_business(
            {
                "business_id": biz["business_id"],
                "business_name": biz["business_name"],
                "doc_id": doc_id,
            }
        )

    # 逐个 BM 拉取资源
    for i, biz in enumerate(businesses, 1):
        business_id = biz["business_id"]
        logging.info(
            f"  [{i}/{len(businesses)}] 处理 Business: "
            f"{business_id} ({biz['business_name']})"
        )
        _fetch_bm_resources(business_id, collected)

    logging.info(
        f"[{token_type} {doc_id}] BM 处理完成（{len(businesses)} 个 Business）"
    )
