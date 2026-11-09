"""
部门名称重命名一次性脚本。

投放一组 -> 投放部
投放三组 -> TF
投放二组 -> 无限部

每个函数处理一个表。run() 里按顺序跑一遍。
"""

import logging
from datetime import date

import conf.log_conf  # noqa: F401  触发 dictConfig
from db.clients import mongo_client, mongo_client_user, mysql_client

DEPT_MAP = {
    "投放一组": "投放部",
    "投放三组": "TF",
    "投放二组": "无限部",
}


def rename_user_department():
    """user.user: department 字段 (字符串) 全量替换"""
    col = mongo_client_user["user"]
    for old, new in DEPT_MAP.items():
        result = col.update_many({"department": old}, {"$set": {"department": new}})
        logging.info(f"[user.user.department] {old} -> {new}: matched={result.matched_count} modified={result.modified_count}")


def rename_user_departments_array():
    """user.user: departments 数组中的元素逐个替换"""
    col = mongo_client_user["user"]
    for old, new in DEPT_MAP.items():
        result = col.update_many(
            {"departments": old},
            {"$set": {"departments.$[elem]": new}},
            array_filters=[{"elem": {"$eq": old}}],
        )
        logging.info(f"[user.user.departments[]] {old} -> {new}: matched={result.matched_count} modified={result.modified_count}")


def rename_department_config():
    """plat.department_config: name 字段(部门主数据)"""
    col = mongo_client["department_config"]
    for old, new in DEPT_MAP.items():
        result = col.update_many({"name": old}, {"$set": {"name": new}})
        logging.info(f"[plat.department_config.name] {old} -> {new}: matched={result.matched_count} modified={result.modified_count}")


def rename_accounts():
    """plat.accounts: 开发者配置的 department 数组,逐元素替换"""
    col = mongo_client["accounts"]
    for old, new in DEPT_MAP.items():
        result = col.update_many(
            {"department": old},
            {"$set": {"department.$[elem]": new}},
            array_filters=[{"elem": {"$eq": old}}],
        )
        logging.info(f"[plat.accounts.department[]] {old} -> {new}: matched={result.matched_count} modified={result.modified_count}")


def rename_doris_ad_daily_detail():
    """Doris: ad.ad_daily_detail.department"""
    _doris_rename_dept("ad_daily_detail")


def rename_doris_ad_hourly_detail():
    """Doris: ad.ad_hourly_detail.department"""
    _doris_rename_dept("ad_hourly_detail")


def rename_doris_ad_hourly_summary():
    """Doris: ad.ad_hourly_summary.department"""
    _doris_rename_dept("ad_hourly_summary")


def _month_ranges(start: date, end: date):
    """生成 [(month_start, next_month_start), ...], 左闭右开"""
    cur = date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    while cur <= last:
        if cur.month == 12:
            nxt = date(cur.year + 1, 1, 1)
        else:
            nxt = date(cur.year, cur.month + 1, 1)
        yield cur, nxt
        cur = nxt


def _doris_rename_dept(table: str):
    with mysql_client.session() as cur:
        cur.execute(f"SELECT MIN(`date`), MAX(`date`) FROM {table} WHERE department IS NOT NULL")
        row = cur.fetchone()
        if not row or row[0] is None:
            logging.info(f"[doris.{table}] 没有 department 数据, 跳过")
            return
        min_d, max_d = row[0], row[1]
        if hasattr(min_d, "date"):
            min_d = min_d.date()
        if hasattr(max_d, "date"):
            max_d = max_d.date()
        logging.info(f"[doris.{table}] date 范围: {min_d} ~ {max_d}")

        for m_start, m_end in _month_ranges(min_d, max_d):
            for old, new in DEPT_MAP.items():
                cur.execute(
                    f"UPDATE {table} SET department=%s "
                    f"WHERE department=%s AND `date` >= %s AND `date` < %s",
                    (new, old, m_start, m_end),
                )
                logging.info(
                    f"[doris.{table}.department] {m_start:%Y-%m} {old} -> {new}: affected={cur.rowcount}"
                )


def run():
    rename_user_department()
    rename_user_departments_array()
    rename_department_config()
    rename_accounts()
    rename_doris_ad_daily_detail()
    rename_doris_ad_hourly_detail()


if __name__ == "__main__":
    run()
