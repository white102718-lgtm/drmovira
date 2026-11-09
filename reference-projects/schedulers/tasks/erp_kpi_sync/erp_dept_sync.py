# -*- coding:utf-8 -*-
"""ERP 部门同步: 把 ERP sys_dept 中 dept_id=100 及其整个子树全量对账到 mongo plat.department_config。

department_config 以 name 为业务主键,parent_id 存父部门名称(不是 ID);
同步来源的文档带 erp_dept_id,随 ERP 增删改;与 ERP 同名的存量文档回填 erp_dept_id 认领;
无 erp_dept_id 的手工部门不参与对账,永不被同步删除。
删除与 backend 一致,移入 trash.department_config。
"""
import logging
from datetime import datetime

from db.clients import client, erp_db, mongo_client, mongo_client_user, tz_cst
from utils.common_util import handle_error

_ERP_TENANT_ID = 1
_ROOT_DEPT_ID = 100  # Mpower管理,同步范围 = 该节点及其子树


def _now():
    return datetime.now(tz_cst).strftime("%Y-%m-%d %H:%M:%S")


@handle_error(error_message="ERP 部门同步失败")
def sync_erp_depts_to_mongo():
    rows = erp_db.read(
        "SELECT dept_id, parent_id, dept_name FROM sys_dept "
        f"WHERE tenant_id={_ERP_TENANT_ID} AND del_flag='0' "
        f"AND (dept_id={_ROOT_DEPT_ID} OR ancestors='0,{_ROOT_DEPT_ID}' "
        f"OR ancestors LIKE '0,{_ROOT_DEPT_ID},%')"
    )
    active = {r[0]: {"parent_id": r[1], "name": r[2]} for r in rows}
    if _ROOT_DEPT_ID not in active:
        logging.error(f"ERP 根部门 dept_id={_ROOT_DEPT_ID} 不存在或已删,跳过本轮同步")
        return

    col = mongo_client["department_config"]
    trash_col = client["trash"]["department_config"]
    user_col = mongo_client_user["user"]

    docs = list(col.find({}))
    by_erp = {d["erp_dept_id"]: d for d in docs if d.get("erp_dept_id")}
    by_name = {d["name"]: d for d in docs}

    # 认领: ERP 部门与无 erp_dept_id 的存量文档同名 → 回填 erp_dept_id 纳入对账
    claimed = 0
    for dept_id, info in active.items():
        if dept_id in by_erp:
            continue
        doc = by_name.get(info["name"])
        if doc is not None and not doc.get("erp_dept_id"):
            col.update_one({"_id": doc["_id"]}, {"$set": {"erp_dept_id": dept_id}})
            doc["erp_dept_id"] = dept_id
            by_erp[dept_id] = doc
            claimed += 1
            logging.info(
                f"[ERP-DEPT-SYNC] 认领存量部门 name={info['name']} erp_dept_id={dept_id}"
            )

    # 删除: 带 erp_dept_id 但已不在 ERP 活跃子树 → 删除并移入 trash
    deleted = 0
    for erp_id in list(by_erp):
        if erp_id in active:
            continue
        doc = by_erp.pop(erp_id)
        col.delete_one({"_id": doc["_id"]})
        by_name.pop(doc["name"], None)
        doc["delete_time"] = _now()
        doc["deleted_by"] = "erp_sync"
        trash_col.insert_one(doc)
        deleted += 1
        logging.info(
            f"[ERP-DEPT-SYNC] 删除部门 name={doc['name']} erp_dept_id={erp_id}(已移入 trash)"
        )

    def _parent_name(dept_id, info):
        if dept_id == _ROOT_DEPT_ID:
            return None
        parent = active.get(info["parent_id"])
        if parent is None:
            logging.warning(
                f"[ERP-DEPT-SYNC] name={info['name']} 的父部门 "
                f"dept_id={info['parent_id']} 不在活跃子树,暂挂为顶级"
            )
            return None
        return parent["name"]

    # 更新(先于新增,改名可为新部门腾出名字)
    updated = 0
    for dept_id, info in active.items():
        doc = by_erp.get(dept_id)
        if doc is None:
            continue
        changes = {}
        old_name = doc["name"]
        if info["name"] != old_name:
            other = by_name.get(info["name"])
            if other is not None and other["_id"] != doc["_id"]:
                logging.warning(
                    f"[ERP-DEPT-SYNC] 改名冲突: {old_name} → {info['name']} "
                    f"已被其他文档占用,本轮跳过改名 erp_dept_id={dept_id}"
                )
            else:
                changes["name"] = info["name"]
        parent_name = _parent_name(dept_id, info)
        if parent_name != doc.get("parent_id"):
            changes["parent_id"] = parent_name
        if not changes:
            continue
        changes["update_time"] = _now()
        changes["updated_by"] = "erp_sync"
        col.update_one({"_id": doc["_id"]}, {"$set": changes})
        if "name" in changes:
            # 子部门 parent_id、用户 department/departments 都按名称引用,级联改
            col.update_many(
                {"parent_id": old_name}, {"$set": {"parent_id": changes["name"]}}
            )
            user_col.update_many(
                {"department": old_name}, {"$set": {"department": changes["name"]}}
            )
            user_col.update_many(
                {"departments": old_name}, {"$set": {"departments.$": changes["name"]}}
            )
            by_name.pop(old_name, None)
            doc["name"] = changes["name"]
            by_name[doc["name"]] = doc
        doc["parent_id"] = parent_name
        updated += 1
        logging.info(
            f"[ERP-DEPT-SYNC] 更新部门 erp_dept_id={dept_id} "
            f"name={old_name} → {doc['name']} parent={doc['parent_id']}"
        )

    # 新增
    inserted = 0
    for dept_id, info in active.items():
        if dept_id in by_erp:
            continue
        if info["name"] in by_name:
            logging.warning(
                f"[ERP-DEPT-SYNC] name={info['name']} 已被其他文档占用,"
                f"跳过新增 erp_dept_id={dept_id}"
            )
            continue
        new_doc = {
            "name": info["name"],
            "parent_id": _parent_name(dept_id, info),
            "erp_dept_id": dept_id,
            "create_time": _now(),
            "created_by": "erp_sync",
        }
        col.insert_one(new_doc)
        by_erp[dept_id] = new_doc
        by_name[info["name"]] = new_doc
        inserted += 1
        logging.info(
            f"[ERP-DEPT-SYNC] 新建部门 name={info['name']} "
            f"parent={new_doc['parent_id']} erp_dept_id={dept_id}"
        )

    logging.info(
        f"ERP 部门同步完成: ERP 活跃 {len(active)},认领 {claimed},"
        f"新建 {inserted},更新 {updated},删除 {deleted}"
    )


if __name__ == "__main__":
    from conf.log_conf import init

    init("erp_dept_sync")
    sync_erp_depts_to_mongo()
