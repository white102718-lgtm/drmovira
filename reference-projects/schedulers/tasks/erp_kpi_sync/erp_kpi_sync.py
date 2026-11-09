# -*- coding:utf-8 -*-
"""
ERP KPI 同步: 从 ERP 的 fbad_ad_task + task_kpi_info 把活跃 task 的 KPI
配置迁移到 mongo plat.platform_config / plat.material_category。

- 取 fbad_ad_task 中 task_status IN (0, 1, 2) 的 task,逐个处理。
- 关联 task_kpi_info 拿到每个 task 的 KPI 行(列字段优先,都空时退到 kpi_json)。
- platform_config(_id=task_name) 用 upsert,首次写入才下 create_*。
- 没 KPI / 没 subtask 的 task 也写入 platform_config,对应数组置空。
- 对应的 material_category 首次新建;再跑时,保持 sub_categories 内部
  uuid 不变,只更新文本与 update_time(uuid 可能被前端其他文档引用)。
"""
import functools
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from uuid import uuid4

from bson import ObjectId

from db.clients import erp_db, mongo_client, mongo_client_user, tz_cst
from utils.common_util import handle_error

# 与前端 1:1 的国家中文→二字码映射,源自前端常量文件
_COUNTRY_MAP_PATH = Path(__file__).resolve().parent / "country_code_map.json"


@functools.lru_cache(maxsize=1)
def _load_country_map() -> dict:
    with open(_COUNTRY_MAP_PATH, encoding="utf-8") as f:
        return {item["name"]: item["code"] for item in json.load(f)}


def _resolve_region_code(region_zh: str) -> Optional[str]:
    """ERP 中文国家名 → ISO 二字码;命中不到记 warning 返回 None。"""
    if not region_zh:
        return None
    code = _load_country_map().get(region_zh.strip())
    if code is None:
        logging.warning(f"region '{region_zh}' 未匹配到国家二字码,target_region 写 None")
    return code


def _load_user_real_name_map() -> dict:
    """读取 mongo user.user 集合的 {full_name: real_name} 映射,每次调用都重新查。"""
    m = {
        doc["full_name"]: doc["real_name"]
        for doc in mongo_client_user["user"].find(
            {}, {"full_name": 1, "real_name": 1}
        )
        if doc.get("full_name") and doc.get("real_name")
    }
    if not m:
        logging.warning(
            "user.user 加载到 0 条 full_name→real_name 映射,"
            "optimizer 全部退化为 delivery_operator 原值"
        )
    return m


def _resolve_optimizer(delivery_operator, name_map: dict) -> Optional[str]:
    """delivery_operator → 优先映射到 user.real_name;映射不到保留原值;空返回 None。"""
    if not delivery_operator:
        return None
    op = str(delivery_operator).strip()
    if not op:
        return None
    return name_map.get(op, None)


def _load_dept_map() -> dict:
    """从 ERP sys_dept 加载 {str(dept_id): dept_name}。"""
    rows = erp_db.read("SELECT dept_id, dept_name FROM sys_dept")
    m = {str(did): name for did, name in rows if did is not None and name}
    if not m:
        logging.warning("sys_dept 加载到 0 条映射,internal_team/external_team 全部写 null")
    return m


def _resolve_dept_names(ids_str, dept_map) -> Optional[list]:
    """逗号分隔的 dept_id → dept_name 列表;空或全部映射失败返回 None。"""
    if not ids_str:
        return None
    names = []
    for tok in str(ids_str).split(","):
        did = tok.strip()
        if not did:
            continue
        name = dept_map.get(did)
        if name is None:
            logging.warning(f"dept_id '{did}' 在 sys_dept 未匹配到 dept_name")
            continue
        names.append(name)
    return names if names else None


# calculation_field -> 展示用中文
_FIELD_LABEL = {
    "cpa": "单次成效费用",
    "roasPurchase": "ROAS",
    "costPerUniquePurchase": "单次购物费用",
}

# calculation_symbol -> 比较符;6 单独处理(两者之间)
_SYMBOL_CHAR = {'1': ">", '2': "<", '3': "=", '4': "≥", '5': "≤"}

_KPI_TEXT_SEP = "    "  # 同一个 task 多条 KPI 之间用 4 空格连接


def _format_number(v) -> str:
    """Decimal/float/int/str → 紧凑字符串。去掉小数尾零, None 返回空串。"""
    if v is None:
        return ""
    s = str(v).strip()
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def _format_kpi_row(min_num, max_num, field, symbol, params) -> Optional[str]:
    """单条 task_kpi_info 行 → "ROAS=50" / "30<ROAS<50";字段或符号未知返回 None。"""
    label = _FIELD_LABEL.get(field)
    if label is None:
        return None
    if symbol == '6':
        return f"{_format_number(min_num)}<{label}<{_format_number(max_num)}"
    sym = _SYMBOL_CHAR.get(symbol)
    if sym is None:
        return None
    return f"{label}{sym}{_format_number(params)}"


# fbad_ad_task 取数的列,顺序必须与 Task 字段对齐;两条查询共用一份,加字段只改这里
_TASK_COLUMNS = (
    "task_id", "task_name", "region", "task_status", "start_time",
    "liability_company", "outsourcing_team", "product_info",
)
_TASK_SELECT = f"SELECT {', '.join(_TASK_COLUMNS)} FROM fbad_ad_task "


@dataclass(frozen=True)
class Task:
    task_id: object
    task_name: str
    region: str
    task_status: object
    start_time: object
    liability_company: object
    outsourcing_team: object
    product_info: object

    @classmethod
    def from_row(cls, row):
        # row 列顺序由 _TASK_COLUMNS 决定,只对 name/region 做 trim,其余原样落字段
        tid, name, region, *rest = row
        return cls(tid, (name or "").strip(), (region or "").strip(), *rest)


def _fetch_tasks(task_ids=None):
    # 指定 task_ids 时直接按 id 取,供补数脚本重跑用
    if task_ids:
        quoted = ", ".join(
            "'" + str(tid).replace("'", "''") + "'" for tid in task_ids
        )
        rows = erp_db.read(_TASK_SELECT + f"WHERE task_id IN ({quoted})")
        return [
            Task.from_row(row) for row in rows
            if row[0] is not None and (row[1] or "").strip()
        ]

    # update_time 是 'YYYY-MM-DD HH:MM:SS' 字符串,字典序==时间序,直接字符串比较走索引最快
    start = (datetime.now(tz_cst) - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    rows = list(erp_db.read(_TASK_SELECT + f"WHERE update_time >= '{start}'"))

    # 父 task 未更新但 subtask 更新也要同步:用 subtask 的 task_id 反查 fbad_ad_task,去重后 union
    subtask_id_rows = erp_db.read(
        f"SELECT DISTINCT task_id FROM fbad_ad_subtask WHERE update_time >= '{start}'"
    )
    seen_ids = {row[0] for row in rows if row[0] is not None}
    extra_ids = [tid for (tid,) in subtask_id_rows if tid is not None and tid not in seen_ids]

    if extra_ids:
        quoted = ", ".join(
            "'" + str(tid).replace("'", "''") + "'" for tid in extra_ids
        )
        rows.extend(erp_db.read(_TASK_SELECT + f"WHERE task_id IN ({quoted})"))

    return [
        Task.from_row(row) for row in rows
        if row[0] is not None and (row[1] or "").strip()
    ]


def _fetch_kpi_grouped(task_ids):
    """按 task_id 分组取 task_kpi_info,返回 {task_id: [(min,max,field,symbol,params), ...]}。

    列字段 (calculation_field/calculation_symbol) 都非空 → 用列字段;
    否则退到 kpi_json,取 calculationField/calculationSymbol/computeParams/computeParams2。
    kpi_json 路径下 symbol=6 时区间用 (computeParams, computeParams2),其他 symbol 用 computeParams 当 params。
    """
    if not task_ids:
        return {}
    # task_id 用单引号 quote,MySQL 对数字列会隐式转换;字符串列也安全。
    quoted = ", ".join(
        "'" + str(tid).replace("'", "''") + "'" for tid in task_ids
    )
    rows = erp_db.read(
        "SELECT task_id, min_num, max_num, calculation_field, "
        "calculation_symbol, compute_params, kpi_json "
        f"FROM task_kpi_info WHERE task_id IN ({quoted}) "
        "AND kpi_status=1 AND (calculation_field IS NOT NULL OR kpi_json IS NOT NULL)"
    )
    grouped = {}
    for tid, min_num, max_num, field, symbol, params, kpi_json in rows:
        if field is not None and symbol is not None:
            grouped.setdefault(str(tid), []).append((min_num, max_num, field, symbol, params))
            continue
        if not kpi_json:
            continue
        data = kpi_json if isinstance(kpi_json, dict) else json.loads(kpi_json)
        j_field = data.get("calculationField")
        j_symbol = data.get("calculationSymbol")
        j_p1 = data.get("computeParams")
        j_p2 = data.get("computeParams2")
        grouped.setdefault(str(tid), []).append((j_p1, j_p2, j_field, j_symbol, j_p1))
    return grouped


def _build_kpi_text(kpi_rows) -> str:
    texts = [t for t in (_format_kpi_row(*r) for r in kpi_rows) if t]
    return _KPI_TEXT_SEP.join(texts)


def _fetch_subtasks_grouped(task_ids):
    """按 task_id 分组取 fbad_ad_subtask,返回 {str(task_id): [(subtask_name, delivery_url, delivery_operator, delivery_status, pixel, page_id), ...]}。"""
    if not task_ids:
        return {}
    quoted = ", ".join(
        "'" + str(tid).replace("'", "''") + "'" for tid in task_ids
    )
    rows = erp_db.read(
        "SELECT task_id, subtask_name, delivery_url, delivery_operator, delivery_status, pixel, page_id "
        f"FROM fbad_ad_subtask WHERE task_id IN ({quoted})"
    )
    grouped = {}
    for tid, sub_name, url, op, status, pixel, page_id in rows:
        grouped.setdefault(str(tid), []).append((sub_name, url, op, status, pixel, page_id))
    return grouped


def _upsert_agent_line_config(subtask_name, delivery_url, delivery_operator, delivery_status, pixel, page_id, now):
    """upsert 单条 agent_line_config。
    package_url / optimizer / pixel_name / page_id 非空才 $set,空时保留旧值;
    history_package_urls 仅在 delivery_url 非空时 $addToSet 追加去重;
    ERP pixel 列存在三种形态:纯名字 / 纯数字 ID / "名字+空白+ID" 拼接,
    只有纯名字写入 pixel_name,后两种视为脏值跳过。"""
    set_fields = {
        "enabled": (str(delivery_status).strip() == "1"),
        "update_time": now,
        "updated_by": "migrate",
    }
    if delivery_url:
        set_fields["package_url"] = delivery_url
    if delivery_operator:
        set_fields["optimizer"] = delivery_operator
    pixel = (str(pixel) if pixel is not None else "").strip()
    if pixel and not pixel.isdigit() and len(pixel.split()) == 1:
        set_fields["pixel_name"] = pixel
    page_id = (str(page_id) if page_id is not None else "").strip()
    if page_id:
        set_fields["page_id"] = page_id

    set_on_insert = {
        "create_time": now,
        "created_by": "migrate",
        "auto_run": False,
        "budget_cap": None,
        "budget_floor": None,
        "is_send": False,
        "objective": None,
        "package_name": None,
        "package_type": "Store",
    }
    if "pixel_name" not in set_fields:  # $set/$setOnInsert 不能同键
        set_on_insert["pixel_name"] = None

    update = {"$set": set_fields, "$setOnInsert": set_on_insert}
    if delivery_url:
        update["$addToSet"] = {"history_package_urls": delivery_url}

    mongo_client["agent_line_config"].update_one({"_id": subtask_name}, update, upsert=True)


def _upsert_material_category(existing_mc_id, kpi_text, now):
    """
    按 sub_categories.name == 'KPI' 定位:命中 → 就地改它的 contents[0].name(保住 uuid);
    文档存在但没 KPI sub_category → $push 一条新的,不动其他 sub_category;
    文档完全不存在 → 新建。
    """
    mc_col = mongo_client["material_category"]

    if existing_mc_id is not None:
        # 1) 已有 KPI sub_category → positional $ 就地更新
        result = mc_col.update_one(
            {"_id": ObjectId(existing_mc_id), "sub_categories.name": "KPI"},
            {
                "$set": {
                    "sub_categories.$.contents.0.name": kpi_text,
                    "update_time": now,
                    "updated_by": "migrate",
                }
            },
        )
        if result.matched_count:
            return existing_mc_id

        # 2) 文档存在但没 KPI sub_category → push 一条,不影响其他 sub_category
        push_result = mc_col.update_one(
            {"_id": ObjectId(existing_mc_id)},
            {
                "$push": {
                    "sub_categories": {
                        "id": str(uuid4()),
                        "name": "KPI",
                        "contents": [
                            {
                                "id": str(uuid4()),
                                "type": None,
                                "text": None,
                                "name": kpi_text,
                                "remark": None,
                            }
                        ],
                    }
                },
                "$set": {
                    "update_time": now,
                    "updated_by": "migrate",
                },
            },
        )
        if push_result.matched_count:
            return existing_mc_id

        logging.warning(
            f"material_category 旧 id {existing_mc_id} 未匹配到文档,改为新建"
        )

    new_doc = {
        "name": "产品",
        "sub_categories": [
            {
                "id": str(uuid4()),
                "name": "KPI",
                "contents": [
                    {
                        "id": str(uuid4()),
                        "type": None,
                        "text": None,
                        "name": kpi_text,
                        "remark": None,
                    }
                ],
            }
        ],
        "create_time": now,
        "update_time": now,
        "created_by": "migrate",
        "updated_by": "migrate",
    }
    return mc_col.insert_one(new_doc).inserted_id


def _upsert_platform_config(task: Task, *, region, material_category_ids, agent_lines, kpi_text, internal_team, external_team, now):
    """material_category_ids / agent_lines 非空时 $addToSet 追加去重;空时不动该字段。
    kpi_text / internal_team / external_team / product_info 同理:非空才 $set,空时不动。
    start_time / product_info 等原样透传字段直接从 task 读,新增这类字段无需改本签名。"""
    enabled = (str(task.task_status).strip() == "1")
    set_fields = {
        "enabled": enabled,
        "visible": enabled,
        "update_time": now,
        "updated_by": "migrate",
    }
    if kpi_text:
        set_fields["kpi_text"] = kpi_text
    if internal_team:
        set_fields["internal_team"] = internal_team
    if external_team:
        set_fields["external_team"] = external_team
    if task.start_time:
        set_fields["start_time"] = task.start_time.strftime("%Y-%m-%d %H:%M:%S")
    if task.product_info:
        set_fields["product_info"] = task.product_info

    update = {
        "$set": set_fields,
        "$setOnInsert": {
            "create_time": now,
            "created_by": "migrate",
        },
    }
    add_to_set = {}
    if region:
        add_to_set["target_region"] = {"$each": [region]}
    if material_category_ids:
        add_to_set["material_category_ids"] = {"$each": material_category_ids}
    if agent_lines:
        add_to_set["agent_lines"] = {"$each": agent_lines}
    if add_to_set:
        update["$addToSet"] = add_to_set

    mongo_client["platform_config"].update_one(
        {"_id": task.task_name}, update, upsert=True,
    )


@handle_error(error_message="ERP KPI 同步失败")
def sync_erp_kpi_to_mongo(task_ids=None):
    tasks = _fetch_tasks(task_ids)
    if not tasks:
        logging.info("fbad_ad_task 前半小时无更新记录,跳过")
        return

    user_real_name_map = _load_user_real_name_map()
    dept_map = _load_dept_map()
    task_ids = [t.task_id for t in tasks]
    kpi_grouped = _fetch_kpi_grouped(task_ids)
    subtask_grouped = _fetch_subtasks_grouped(task_ids)
    now = datetime.now(tz_cst).strftime("%Y-%m-%d %H:%M:%S")
    pc_col = mongo_client["platform_config"]

    total = len(tasks)
    step = max(total // 10, 1)  # 大约 10 次进度日志
    logging.info(f"ERP KPI 同步开始: 共 {total} 个 task")

    failed = 0
    for i, task in enumerate(tasks, 1):
        tid = task.task_id
        # 收集有效 subtask;没 subtask 就是空数组
        subtasks = []
        for sub_name, url, op, status, pixel, page_id in subtask_grouped.get(str(tid), []):
            sub_name = (sub_name or "").strip()
            url = (url or "").strip()
            if not sub_name or not url:
                logging.warning(
                    f"subtask 数据缺失 (task_id={tid}, subtask_name='{sub_name}', "
                    f"delivery_url='{url}'),跳过"
                )
                continue
            subtasks.append((sub_name, url, op, status, pixel, page_id))

        # 单 task 失败只跳过自己;先写 platform 挂关联、后写线配置,
        # platform 失败时该 task 什么都不写,不产生孤儿代理线
        try:
            # KPI → upsert material_category;没 KPI 时 material_category_ids 留空
            kpi_text = _build_kpi_text(kpi_grouped.get(str(tid), []))
            material_category_ids = []
            if kpi_text:
                existing = pc_col.find_one(
                    {"_id": task.task_name}, {"material_category_ids": 1}
                )
                existing_mc_id = None
                if existing:
                    ids = existing.get("material_category_ids") or []
                    existing_mc_id = ids[0] if ids else None
                mc_id = _upsert_material_category(existing_mc_id, kpi_text, now)
                material_category_ids = [str(mc_id)]

            _upsert_platform_config(
                task,
                region=_resolve_region_code(task.region),
                material_category_ids=material_category_ids,
                agent_lines=[s[0] for s in subtasks],
                kpi_text=kpi_text,
                internal_team=_resolve_dept_names(task.liability_company, dept_map),
                external_team=_resolve_dept_names(task.outsourcing_team, dept_map),
                now=now,
            )

            for sub_name, url, op, status, pixel, page_id in subtasks:
                _upsert_agent_line_config(
                    sub_name, url, _resolve_optimizer(op, user_real_name_map),
                    status, pixel, page_id, now,
                )
        except Exception:
            failed += 1
            logging.exception(f"task {task.task_name} 同步失败,跳过")

        if i % step == 0 and i != total:
            logging.info(f"  进度 {i}/{total}")

    logging.info(f"ERP KPI 同步完成: 处理 task={total}, 失败={failed}")


if __name__ == "__main__":
    from conf.log_conf import init

    init("erp_kpi_sync")
    sync_erp_kpi_to_mongo()
