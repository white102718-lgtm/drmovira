# -*- coding:utf-8 -*-
"""ERP 用户同步: 把 ERP sys_user(tenant_id=1)全量对账到 mongo user.user。

以 erp_user_id 关联,存量文档(JIT / 手工建)按 username/phone 回填认领;
ERP 为唯一真源: 新增建档(结构与 backend JIT 一致)、信息变更全量覆盖
(含 roles,但 departments 数据权限仅建档时初始化、存量不覆盖)、
逻辑删除(del_flag='2')硬删文档、停用(status='1')置 status=0。
认领不上且无 erp_user_id 的文档不参与对账,永不被同步删除。
real_name 有唯一索引,撞名时跳过并告警。
"""
import logging
from datetime import datetime

from db.clients import erp_db, mongo_client_user, tz_cst
from utils.common_util import handle_error

# 与 auth-server 登录查询一致: tenant_id=1
_ERP_TENANT_ID = 1

# sys_user_role 只认这两个角色,与 user_type 映射的角色叠加;
# backend JIT 建档仍按旧规则(OIDC claims 无 role_id),由本同步每轮覆盖纠正
_ERP_ROLE_TO_LOCAL = {3: "operator", 4: "creator"}  # 3=投放师 4=素材师


def _now():
    return datetime.now(tz_cst).strftime("%Y-%m-%d %H:%M:%S")


def _map_roles_and_depts(user_type, dept_name, erp_role_ids):
    """ERP user_type + sys_user_role → 本系统 roles(可叠加多个)+ departments。"""
    roles = []
    if user_type in ("SUPER_ADMIN", "CREATOR"):
        roles.append("admin")
    elif user_type == "DEPT_ADMIN":
        roles.append("operator_leader")
    roles += [v for k, v in _ERP_ROLE_TO_LOCAL.items() if k in erp_role_ids]
    if not roles:
        roles = ["operator"]
    if user_type in ("SUPER_ADMIN", "CREATOR"):
        return roles, ["全部"]
    return roles, [dept_name] if dept_name else []


@handle_error(error_message="ERP 用户同步失败")
def sync_erp_users_to_mongo():
    rows = erp_db.read(
        "SELECT u.user_id, u.user_name, u.nick_name, u.name_abbr, u.user_type, "
        "u.status, u.del_flag, d.dept_name "
        "FROM sys_user u LEFT JOIN sys_dept d ON u.dept_id = d.dept_id "
        f"WHERE u.tenant_id={_ERP_TENANT_ID}"
    )
    if not rows:
        logging.error("sys_user 全量查询为空,跳过本轮同步")
        return
    role_rows = erp_db.read(
        "SELECT ur.user_id, ur.role_id "
        "FROM sys_user_role ur INNER JOIN sys_user u ON ur.user_id = u.user_id "
        f"WHERE u.tenant_id={_ERP_TENANT_ID}"
    )
    role_ids_by_user = {}
    for user_id, role_id in role_rows:
        role_ids_by_user.setdefault(user_id, set()).add(role_id)

    erp_active = {}
    # 认领用两级映射: 活跃行绝对优先(username 和 phone 都查完活跃才查已删行),
    # 否则老 username 撞上 ERP 已删行会把换过账号名的同一个人误删重建
    erp_active_by_name = {}
    erp_deleted_by_name = {}
    for user_id, user_name, nick_name, name_abbr, user_type, status, del_flag, dept_name in rows:
        if del_flag == "0":
            erp_active[user_id] = {
                "user_name": user_name,
                "nick_name": nick_name,
                "name_abbr": name_abbr,
                "user_type": user_type,
                "status": status,
                "dept_name": dept_name,
                "role_ids": role_ids_by_user.get(user_id, set()),
            }
            erp_active_by_name[user_name] = user_id
        else:
            erp_deleted_by_name.setdefault(user_name, user_id)

    col = mongo_client_user["user"]
    docs = list(col.find({}))
    by_erp = {}
    real_name_owner = {}
    for d in docs:
        if d.get("erp_user_id"):
            by_erp[d["erp_user_id"]] = d
        if d.get("real_name"):
            real_name_owner[d["real_name"]] = d["_id"]

    # 认领: 无 erp_user_id 的存量文档按 username/phone 匹配 ERP user_name 回填
    claimed = 0
    for d in docs:
        if d.get("erp_user_id"):
            continue
        uid = (
            erp_active_by_name.get(d.get("username"))
            or erp_active_by_name.get(d.get("phone"))
            or erp_deleted_by_name.get(d.get("username"))
            or erp_deleted_by_name.get(d.get("phone"))
        )
        if uid is None or uid in by_erp:
            continue
        col.update_one({"_id": d["_id"]}, {"$set": {"erp_user_id": uid}})
        d["erp_user_id"] = uid
        by_erp[uid] = d
        claimed += 1

    # 删除: 带 erp_user_id 但 ERP 已逻辑删(或行已不存在)→ 硬删,全文打进日志便于恢复
    deleted = 0
    for uid in list(by_erp):
        if uid in erp_active:
            continue
        doc = by_erp.pop(uid)
        col.delete_one({"_id": doc["_id"]})
        real_name_owner.pop(doc.get("real_name"), None)
        deleted += 1
        logging.info(
            f"[ERP-USER-SYNC] 删除用户(ERP 已删) username={doc.get('username')} "
            f"erp_user_id={uid} doc={doc}"
        )

    inserted = updated = skipped_dup = 0
    for uid, info in erp_active.items():
        nick_name = info["nick_name"] or info["user_name"]
        name_abbr = info["name_abbr"] or nick_name
        roles, departments = _map_roles_and_depts(info["user_type"], info["dept_name"], info["role_ids"])
        status = 1 if info["status"] == "0" else 0
        doc = by_erp.get(uid)

        if doc is None:
            if name_abbr in real_name_owner:
                logging.warning(
                    f"[ERP-USER-SYNC] real_name={name_abbr} 已存在,跳过新建 "
                    f"username={info['user_name']} dept={info['dept_name']}"
                    f"(可在 ERP 补 name_abbr 区分)"
                )
                skipped_dup += 1
                continue
            new_doc = {
                "username": info["user_name"],
                "real_name": name_abbr,
                "full_name": nick_name,
                "phone": info["user_name"],
                "roles": roles,
                "department": info["dept_name"],
                "departments": departments,
                "status": status,
                "create_time": _now(),
                "provisioned_by": "erp_sync",
                "erp_user_id": uid,
            }
            col.insert_one(new_doc)
            by_erp[uid] = new_doc
            real_name_owner[name_abbr] = new_doc["_id"]
            inserted += 1
            logging.info(
                f"[ERP-USER-SYNC] 新建用户 username={info['user_name']} "
                f"full_name={nick_name} real_name={name_abbr} "
                f"user_type={info['user_type']} dept={info['dept_name']} "
                f"roles={roles} departments={departments} status={status}"
            )
            continue

        desired = {
            "username": info["user_name"],
            "phone": info["user_name"],
            "full_name": nick_name,
            "real_name": name_abbr,
            "department": info["dept_name"],
            "status": status,
        }  # departments(数据权限)只在建档时给初值,存量不覆盖,允许本地手动调整
        owner = real_name_owner.get(name_abbr)
        if name_abbr != doc.get("real_name") and owner is not None and owner != doc["_id"]:
            logging.warning(
                f"[ERP-USER-SYNC] real_name={name_abbr} 已被其他用户占用,"
                f"本轮不改名 username={info['user_name']}"
            )
            desired.pop("real_name")
        changes = {k: v for k, v in desired.items() if doc.get(k) != v}
        if not changes:
            continue
        col.update_one({"_id": doc["_id"]}, {"$set": changes})
        if "real_name" in changes:
            real_name_owner.pop(doc.get("real_name"), None)
            real_name_owner[name_abbr] = doc["_id"]
        doc.update(changes)
        updated += 1
        logging.info(
            f"[ERP-USER-SYNC] 更新用户 username={info['user_name']} changes={changes}"
        )

    logging.info(
        f"ERP 用户同步完成: ERP 活跃 {len(erp_active)},认领 {claimed},"
        f"新建 {inserted},更新 {updated},删除 {deleted},重名跳过 {skipped_dup}"
    )


if __name__ == "__main__":
    from conf.log_conf import init

    init("erp_user_sync")
    sync_erp_users_to_mongo()
