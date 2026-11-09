from datetime import datetime, timedelta, timezone
import re
from typing import Any, Dict, List, Optional

from bson import ObjectId

from app.db.mongo import cols, user_cols

ASSET_TYPE_AD_ACCOUNT = "ad_account"
ASSET_TYPE_PAGE = "page"

assignments_col = cols.fb_asset_assignments
user_col = user_cols.user
ad_accounts_col = cols.fb_ad_accounts
pages_col = cols.fb_pages
system_users_col = cols.fb_system_users

tz_cst = timezone(timedelta(hours=8))


async def _resolve_user(user_id: str) -> Dict[str, Any]:
    user = await user_col.find_one(
        {"_id": ObjectId(user_id)},
        {"full_name": 1, "department": 1},
    )
    return {
        "user_id": str(user["_id"]),
        "full_name": user["full_name"],
        "department": user.get("department"),
    }


def _normalize_assets(assets: Optional[List[Dict[str, str]]]) -> List[Dict[str, str]]:
    if not assets:
        return []

    asset_map: Dict[str, Dict[str, str]] = {}
    for asset in assets:
        asset_map[asset["id"]] = {"id": asset["id"], "name": asset["name"]}
    return list(asset_map.values())


async def filter_assets_in_system_users(
    assets: List[Dict[str, str]], field: str, label: str
) -> tuple[List[Dict[str, str]], Optional[str], List]:
    """校验资产 id 是否在 fb_system_users.<field> 下,剔除未关联的并返回提示及命中的系统用户 _id。"""
    payload_ids = {asset["id"] for asset in assets}
    system_users = await system_users_col.find(
        {f"{field}.id": {"$in": list(payload_ids)}},
        {"_id": 1, f"{field}.id": 1},
    ).to_list(length=None)
    found_ids = {
        a["id"]
        for su in system_users
        for a in (su.get(field) or [])
        if a.get("id") in payload_ids
    }
    missing_ids = payload_ids - found_ids
    warning = None
    if missing_ids:
        id_to_name = {asset["id"]: asset["name"] for asset in assets}
        names = "、".join(id_to_name[i] for i in sorted(missing_ids))
        warning = f"{label} {names} 未关联任何系统用户，已自动剔除"
        assets = [asset for asset in assets if asset["id"] not in missing_ids]
    return assets, warning, [su["_id"] for su in system_users]


async def _build_asset_maps(
    records: List[Dict[str, Any]],
) -> tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, str]]]:
    account_ids = list(
        {
            asset["id"]
            for record in records
            for asset in record.get("ad_accounts") or []
            if asset.get("id")
        }
    )
    page_ids = list(
        {
            asset["id"]
            for record in records
            for asset in record.get("pages") or []
            if asset.get("id")
        }
    )

    account_map: Dict[str, Dict[str, str]] = {}
    page_map: Dict[str, Dict[str, str]] = {}

    if account_ids:
        async for account in ad_accounts_col.find(
            {"_id": {"$in": account_ids}},
            {"_id": 1, "name": 1},
        ):
            account_map[account["_id"]] = {
                "id": account["_id"],
                "name": account.get("name") or account["_id"],
            }

    if page_ids:
        async for page in pages_col.find(
            {"_id": {"$in": page_ids}},
            {"_id": 1, "name": 1, "picture": 1},
        ):
            picture = page.get("picture")
            if isinstance(picture, dict):
                picture = picture.get("url", "")
            page_map[page["_id"]] = {
                "id": page["_id"],
                "name": page.get("name") or page["_id"],
                "picture": picture or "",
            }

    return account_map, page_map


async def _list_department_user_ids(department: str) -> List[str]:
    user_ids: List[str] = []
    async for user in user_col.find({"department": department}, {"_id": 1}):
        user_ids.append(str(user["_id"]))
    return user_ids


async def _build_user_map(user_ids: List[Optional[str]]) -> Dict[str, Dict[str, Optional[str]]]:
    valid_user_ids = [user_id for user_id in user_ids if user_id]
    if not valid_user_ids:
        return {}

    user_map: Dict[str, Dict[str, Optional[str]]] = {}
    async for user in user_col.find(
        {"_id": {"$in": [ObjectId(user_id) for user_id in valid_user_ids]}},
        {"full_name": 1, "department": 1},
    ):
        user_map[str(user["_id"])] = {
            "full_name": user.get("full_name"),
            "department": user.get("department"),
        }
    return user_map


def _serialize_assignment(
    record: Dict[str, Any],
    user_map: Dict[str, Dict[str, Optional[str]]],
    account_map: Dict[str, Dict[str, str]],
    page_map: Dict[str, Dict[str, str]],
) -> Dict[str, Any]:
    item = dict(record)
    user_id = item.get("user_id")
    user_info = user_map.get(user_id, {})
    accounts = []
    for account in item.get("ad_accounts") or []:
        account_id = account.get("id")
        accounts.append(account_map.get(account_id, account))

    pages = []
    for page in item.get("pages") or []:
        page_id = page.get("id")
        pages.append(page_map.get(page_id, page))

    item["_id"] = str(item["_id"])
    item.pop("ad_accounts", None)
    item["user_name"] = item.get("full_name") or user_info.get("full_name")
    item["department"] = item.get("department") or user_info.get("department")
    item["ad_accounts"] = accounts
    item["pages"] = pages
    return item


def _build_stats_items(ad_accounts: List[Dict[str, str]], pages: List[Dict[str, str]]) -> List[dict]:
    return [
        {"asset_type": ASSET_TYPE_AD_ACCOUNT, "count": len(ad_accounts)},
        {"asset_type": ASSET_TYPE_PAGE, "count": len(pages)},
    ]


async def _create_assignment(
    user_id: Optional[str],
    full_name: Optional[str],
    department: Optional[str],
    remark: Optional[str],
    ad_accounts: Optional[List[Dict[str, str]]],
    pages: Optional[List[Dict[str, str]]],
    operator: str,
) -> dict:
    now = datetime.now(tz_cst)
    result = await assignments_col.insert_one(
        {
            "user_id": user_id,
            "full_name": full_name,
            "department": department,
            "remark": remark,
            "ad_accounts": _normalize_assets(ad_accounts),
            "pages": _normalize_assets(pages),
            "created_at": now,
            "created_by": operator,
            "updated_at": now,
            "updated_by": operator,
        }
    )
    record = await assignments_col.find_one({"_id": result.inserted_id})
    user_map = await _build_user_map([record.get("user_id")])
    account_map, page_map = await _build_asset_maps([record])
    return _serialize_assignment(record, user_map, account_map, page_map)


def _build_department_scope_query(department: str, department_user_ids: List[str]) -> Dict[str, Any]:
    return {
        "$or": [
            {"user_id": {"$in": department_user_ids}},
            {"user_id": None, "department": department},
        ]
    }


async def assigned_asset_ids(
    department: Optional[str], user_id: Optional[str] = None
) -> tuple[set, set]:
    """资产关联中分配的 (广告账户 ID 集合, 主页 ID 集合)。

    user_id 传入时限定该用户本人的记录 + 部门共享记录(user_id=None);
    否则取整个部门(全体成员 + 部门共享)。
    """
    if user_id:
        scope = {
            "$or": [
                {"user_id": user_id},
                {"user_id": None, "department": department},
            ]
        }
    else:
        scope = _build_department_scope_query(
            department, await _list_department_user_ids(department)
        )
    account_ids: set = set()
    page_ids: set = set()
    async for assn in assignments_col.find(
        scope, {"ad_accounts.id": 1, "pages.id": 1}
    ):
        account_ids.update(
            a["id"] for a in assn.get("ad_accounts") or [] if a.get("id")
        )
        page_ids.update(p["id"] for p in assn.get("pages") or [] if p.get("id"))
    return account_ids, page_ids


async def save_assignments(
    user_ids: List[str],
    department: str,
    remark: Optional[str],
    ad_accounts: Optional[List[Dict[str, str]]],
    pages: Optional[List[Dict[str, str]]],
    operator: str,
    error_message: list,
    bypass_department: bool = False,
) -> List[dict]:
    items: List[dict] = []
    unique_user_ids = list(dict.fromkeys([user_id for user_id in user_ids if user_id]))

    if not unique_user_ids:
        existing = await assignments_col.find_one(
            {"user_id": None, "department": department}
        )
        if existing:
            error_message.append("用户ID已存在: null")
            return items
        return [
            await _create_assignment(
                user_id=None,
                full_name=None,
                department=department,
                remark=remark,
                ad_accounts=ad_accounts,
                pages=pages,
                operator=operator,
            )
        ]

    for user_id in unique_user_ids:
        existing = await assignments_col.find_one(
            {"user_id": user_id}
        )
        if existing:
            error_message.append(f"用户ID已存在: {user_id}")
            continue
        user = await _resolve_user(user_id)
        if not bypass_department and user["department"] != department:
            error_message.append(f"用户 {user['full_name']} 不在你的部门")
            continue
        items.append(
            await _create_assignment(
                user_id=user["user_id"],
                full_name=user["full_name"],
                department=None,
                remark=remark,
                ad_accounts=ad_accounts,
                pages=pages,
                operator=operator,
            )
        )
    return items


async def resolve_record_department(record_id: str) -> Optional[str]:
    record = await assignments_col.find_one(
        {"_id": ObjectId(record_id)},
        {"user_id": 1, "department": 1},
    )
    if not record:
        return None
    if record.get("user_id"):
        user = await user_col.find_one(
            {"_id": ObjectId(record["user_id"])},
            {"department": 1},
        )
        return user.get("department") if user else None
    return record.get("department")


async def update_assignment(
    record_id: str,
    user_id: Optional[str],
    remark: Optional[str],
    ad_accounts: Optional[List[Dict[str, str]]],
    pages: Optional[List[Dict[str, str]]],
    operator: str,
) -> Optional[dict]:
    record = await assignments_col.find_one(
        {"_id": ObjectId(record_id)}
    )
    if not record:
        return None

    update_set: Dict[str, Any] = {
        "updated_at": datetime.now(tz_cst),
        "updated_by": operator,
    }

    if user_id is not None:
        user = await _resolve_user(user_id)
        update_set["user_id"] = user["user_id"]
        update_set["full_name"] = user["full_name"]
        update_set["department"] = None
    if remark is not None:
        update_set["remark"] = remark
    if ad_accounts is not None:
        update_set["ad_accounts"] = _normalize_assets(ad_accounts)
    if pages is not None:
        update_set["pages"] = _normalize_assets(pages)

    await assignments_col.update_one(
        {"_id": ObjectId(record_id)},
        {"$set": update_set},
    )
    updated = await assignments_col.find_one(
        {"_id": ObjectId(record_id)}
    )
    user_map = await _build_user_map([updated.get("user_id")])
    account_map, page_map = await _build_asset_maps([updated])
    return _serialize_assignment(updated, user_map, account_map, page_map)


async def delete_assignment(record_id: str) -> bool:
    result = await assignments_col.delete_one(
        {"_id": ObjectId(record_id)}
    )
    return result.deleted_count > 0


async def delete_by_filter(
    user_id: Optional[str],
    department: Optional[str],
    ad_account_id: Optional[str],
    page_id: Optional[str],
) -> int:
    if not any([user_id, department, ad_account_id, page_id]):
        raise ValueError("批量删除必须提供至少一个过滤条件")

    q: Dict[str, Any] = {}
    if department:
        department_user_ids = await _list_department_user_ids(department)
        if user_id:
            if user_id not in department_user_ids:
                return 0
            q["user_id"] = user_id
        else:
            q.update(_build_department_scope_query(department, department_user_ids))
    elif user_id:
        q["user_id"] = user_id

    if ad_account_id:
        q["ad_accounts.id"] = ad_account_id
    if page_id:
        q["pages.id"] = page_id

    result = await assignments_col.delete_many(q)
    return result.deleted_count


async def list_assignments(
    page: int,
    page_size: int,
    user_id: Optional[str] = None,
    department: Optional[str] = None,
    ad_account_name: Optional[str] = None,
    page_id: Optional[str] = None,
) -> dict:
    q: Dict[str, Any] = {}
    if department:
        department_user_ids = await _list_department_user_ids(department)
        if user_id:
            if user_id not in department_user_ids:
                return {"total": 0, "items": [], "page": page, "page_size": page_size}
            q["user_id"] = user_id
        else:
            q.update(_build_department_scope_query(department, department_user_ids))
    elif user_id:
        q["user_id"] = user_id

    if ad_account_name:
        q["ad_accounts.name"] = {"$regex": re.escape(ad_account_name), "$options": "i"}
    if page_id:
        q["pages.id"] = page_id

    skip = (page - 1) * page_size
    total = await assignments_col.count_documents(q)
    records = await (
        assignments_col.find(q).sort("updated_at", -1).skip(skip).limit(page_size)
    ).to_list(length=page_size)
    user_map = await _build_user_map([record.get("user_id") for record in records])
    account_map, page_map = await _build_asset_maps(records)
    items = [
        _serialize_assignment(record, user_map, account_map, page_map)
        for record in records
    ]
    return {"total": total, "items": items, "page": page, "page_size": page_size}


async def aggregate_stats(department: Optional[str] = None) -> dict:
    q: Dict[str, Any] = {}
    if department:
        q.update(
            _build_department_scope_query(
                department,
                await _list_department_user_ids(department),
            )
        )

    records = await assignments_col.find(q).to_list(length=None)
    user_map = await _build_user_map([record.get("user_id") for record in records])

    by_department_map: Dict[Optional[str], Dict[str, set]] = {}
    by_user: List[dict] = []

    for record in records:
        user_id = record.get("user_id")
        user_info = user_map.get(user_id, {})
        record_department = record.get("department") or user_info.get("department")
        ad_accounts = record.get("ad_accounts") or []
        pages = record.get("pages") or []

        by_user.append(
            {
                "user_id": user_id,
                "full_name": record.get("full_name") or user_info.get("full_name"),
                "department": record_department,
                "items": _build_stats_items(ad_accounts, pages),
                "total": len(ad_accounts) + len(pages),
            }
        )

        if record_department not in by_department_map:
            by_department_map[record_department] = {
                ASSET_TYPE_AD_ACCOUNT: set(),
                ASSET_TYPE_PAGE: set(),
            }

        by_department_map[record_department][ASSET_TYPE_AD_ACCOUNT].update(
            asset["id"] for asset in ad_accounts
        )
        by_department_map[record_department][ASSET_TYPE_PAGE].update(
            asset["id"] for asset in pages
        )

    by_department = []
    for department_name, asset_map in by_department_map.items():
        ad_count = len(asset_map[ASSET_TYPE_AD_ACCOUNT])
        page_count = len(asset_map[ASSET_TYPE_PAGE])
        by_department.append(
            {
                "department": department_name,
                "items": [
                    {"asset_type": ASSET_TYPE_AD_ACCOUNT, "count": ad_count},
                    {"asset_type": ASSET_TYPE_PAGE, "count": page_count},
                ],
                "total": ad_count + page_count,
            }
        )

    return {"by_department": by_department, "by_user": by_user}
