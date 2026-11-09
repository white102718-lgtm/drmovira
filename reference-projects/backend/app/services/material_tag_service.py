"""素材标签的展示态转换：标签 ID → title、扁平 ID → 树。
materials 与 material_commons 两个素材库共用同一套 tree_tags，故放服务层共享。"""

from typing import Any, Dict, Iterable, List

from app.db.mongo import cols

tree_tags = cols.tree_tags


async def _load_titles(tag_ids: Iterable[str], cache: Dict[str, str]) -> None:
    """把缺失的标签标题补进 cache；cache 跨 doc 复用省查询"""
    missing = set(tag_ids) - cache.keys()
    if not missing:
        return
    async for tag_doc in tree_tags.find(
        {"_id": {"$in": list(missing)}}, projection={"title": 1}
    ):
        cache[tag_doc["_id"]] = tag_doc["title"]


async def resolve_tag_titles(doc: Dict[str, Any], cache: Dict[str, str]) -> None:
    """就地把 doc['tags_new'] 的标签 ID 换成 title"""
    if not doc.get("tags_new"):
        return
    await _load_titles(doc["tags_new"], cache)
    doc["tags_new"] = [cache.get(t, t) for t in doc["tags_new"]]


def build_tag_tree(
    tag_ids: Iterable[str], tags_key_name: Dict[str, str]
) -> List[Dict[str, Any]]:
    """扁平标签 ID 列表 → 树。ID 形如 '4-1-1'，用 '-' 分段表达父子层级。
    父级不在列表里的节点提升为根，避免整棵子树丢失。"""
    if not tag_ids:
        return []

    nodes = {
        tag_id: {"key": tag_id, "title": tags_key_name.get(tag_id, tag_id)}
        for tag_id in tag_ids
    }

    roots = []
    for tag_id in tag_ids:
        parent_id = tag_id.rsplit("-", 1)[0] if "-" in tag_id else None
        if parent_id in nodes:
            nodes[parent_id].setdefault("children", []).append(nodes[tag_id])
        else:
            roots.append(nodes[tag_id])

    return sorted(roots, key=lambda x: x["key"])


async def attach_tags_tree(doc: Dict[str, Any], cache: Dict[str, str]) -> None:
    """就地给 doc 加 tags_tree。须在 resolve_tag_titles 之前调用：建树认的是 ID，不是 title。
    只收 tree_tags 里真实存在的标签，已删标签不进树。"""
    if not doc.get("tags_new"):
        return
    tag_ids = set(doc["tags_new"])
    await _load_titles(tag_ids, cache)
    doc["tags_tree"] = build_tag_tree({t for t in tag_ids if t in cache}, cache)
