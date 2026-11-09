import asyncio
import random
import re

from app.db.mongo import cols
from app.services.fb_asset_assignment import assigned_asset_ids


async def dept_allowed_page_ids(department: str) -> set[str]:
    """部门可用主页 ID 集合 = 本部门开发者持有的主页 ∪ fb_asset_assignments 分给该部门的主页。"""
    dev_pages, (_, assigned_pages) = await asyncio.gather(
        _dept_developer_page_ids(department),
        assigned_asset_ids(department),
    )
    return dev_pages | assigned_pages


async def user_allowed_page_ids(department: str, user_id: str) -> set[str]:
    """非 admin 可用主页 = 本部门开发者持有的主页 ∩ 资产关联分给本人(含部门共享记录)的主页。"""
    dev_pages, (_, assigned_pages) = await asyncio.gather(
        _dept_developer_page_ids(department),
        assigned_asset_ids(department, user_id),
    )
    return dev_pages & assigned_pages


async def _dept_developer_page_ids(department: str) -> set[str]:
    """accounts 中本部门开发者(status=1)名下 fb_system_users.pages 的主页 ID 集合。"""
    dept_app_ids = [
        c["app_id"]
        async for c in cols.accounts.find(
            {"status": 1, "department": department}, {"app_id": 1}
        )
        if c.get("app_id")
    ]
    if not dept_app_ids:
        return set()
    page_ids: set[str] = set()
    async for su in cols.fb_system_users.find(
        {"_id": {"$in": dept_app_ids}}, {"pages.id": 1}
    ):
        for p in su.get("pages") or []:
            if p.get("id"):
                page_ids.add(p["id"])
    return page_ids


async def get_personal_pages_by_key(
    personal_ids: list[str],
    department: str | None = None,
    scope_user_id: str | None = None,
) -> dict[str, list[dict]]:
    """按个号 key 返回主页池字典。

    personal_ids 是 person_and_page 字段的 key,形如 '系_<dev_id>_<app_id>'。
    传入 department 时收紧候选池:
      pool[k] = (个号自己 app 名下的主页) ∩ ( 本部门开发者(accounts.department == dept,status=1)
                                              在 fb_system_users 中持有的主页
                                              ∪ fb_asset_assignments 中分配给该部门的主页 )
    再传入 scope_user_id(非 admin)时,∪ 收紧为 ∩ 资产关联分给本人的主页。
    返回 {key: [page_doc, ...]} —— 没有匹配到资源的 key 也会返回空列表,确保前端能区分。
    """
    result: dict[str, list[dict]] = {}
    if not personal_ids:
        return result

    key_to_pair: dict[str, tuple[str, str]] = {}
    for pid in personal_ids:
        if not pid or pid in key_to_pair:
            continue
        parts = pid.split("_")
        if len(parts) < 3 or parts[0] != "系":
            result[pid] = []
            continue
        dev_id, app_id = parts[1], parts[2]
        if not (dev_id and app_id):
            result[pid] = []
            continue
        key_to_pair[pid] = (dev_id, app_id)
        result[pid] = []

    if not key_to_pair:
        return result

    pairs = list({pair for pair in key_to_pair.values()})
    dev_configs = await cols.accounts.find(
        {
            "status": 1,
            "$or": [{"dev_id": d, "app_id": a} for d, a in pairs],
        },
        {"dev_id": 1, "app_id": 1},
    ).to_list(length=None)

    pair_to_app: dict[tuple[str, str], str] = {
        (c["dev_id"], c["app_id"]): c["app_id"]
        for c in dev_configs
        if c.get("dev_id") and c.get("app_id")
    }
    valid_app_ids = list({app for app in pair_to_app.values()})
    if not valid_app_ids:
        return result

    sys_users = await cols.fb_system_users.find(
        {"_id": {"$in": valid_app_ids}}, {"_id": 1, "pages": 1}
    ).to_list(length=None)
    app_to_page_ids: dict[str, list[str]] = {
        s["_id"]: [p["id"] for p in s.get("pages", []) if p.get("id")]
        for s in sys_users
    }

    all_page_ids = {pid for ids in app_to_page_ids.values() for pid in ids}
    if not all_page_ids:
        return result

    page_docs = await cols.fb_pages.find(
        {"_id": {"$in": list(all_page_ids)}},
        {"_id": 1, "name": 1, "picture": 1},
    ).to_list(length=None)
    for p in page_docs:
        pic = p.get("picture")
        if isinstance(pic, dict):
            p["picture"] = pic.get("url", "")
    page_by_id = {p["_id"]: p for p in page_docs}

    allowed_page_ids: set[str] | None = None
    if department:
        allowed_page_ids = await (
            user_allowed_page_ids(department, scope_user_id)
            if scope_user_id
            else dept_allowed_page_ids(department)
        )

    for key, (dev_id, app_id) in key_to_pair.items():
        page_ids = app_to_page_ids.get(app_id, [])
        if allowed_page_ids is not None:
            page_ids = [pid for pid in page_ids if pid in allowed_page_ids]
        result[key] = [page_by_id[pid] for pid in page_ids if pid in page_by_id]
    return result


def assign_pages_for_keys(
    ordered_keys: list[str], pools: dict[str, list[dict]]
) -> list[dict | None]:
    """按输入顺序为每个 key 分配一张主页,跨整批尽量不重复。

    每条命中:从该 key 的 pool 里挑全局 use_count 最小的(同票随机),pool 空则该位置为 None。
    """
    if not ordered_keys:
        return []
    use_count: dict[str, int] = {}
    out: list[dict | None] = [None] * len(ordered_keys)
    indices = list(range(len(ordered_keys)))
    random.shuffle(indices)
    for i in indices:
        candidates = list(pools.get(ordered_keys[i]) or [])
        if not candidates:
            continue
        random.shuffle(candidates)
        chosen = min(candidates, key=lambda p: use_count.get(p.get("_id"), 0))
        page_id = chosen.get("_id")
        if not page_id:
            continue
        out[i] = chosen
        use_count[page_id] = use_count.get(page_id, 0) + 1
    return out


def filter_pools_by_name(
    pools: dict[str, list[dict]], name: str | None
) -> dict[str, list[dict]]:
    if not name:
        return pools
    pattern = re.compile(re.escape(name), re.IGNORECASE)
    return {
        key: [p for p in pages if pattern.search(p.get("name", ""))]
        for key, pages in pools.items()
    }
