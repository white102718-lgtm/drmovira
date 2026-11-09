import logging
import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from conf.log_conf import init
from db.clients import erp_db, mongo_client, mysql_client
from utils import md_open_api

DEPARTMENTS = ["技术部", "无限部"]
# 余额低于预算的此比例才预警
ALERT_BALANCE_RATIO = 0.7
# 充值目标 = 昨日消耗 × 此倍数(账户余额保持在昨日消耗的这个倍数)
GAP_SPEND_D1_MULTIPLIER = 1.5
# account_dsl 为空时充值后余额的上限(美元); 有 account_dsl 则充到 account_dsl
DEFAULT_BALANCE_CAP = 30000
# 同一户两次充值申请的最小间隔(小时)
RECHARGE_COOLDOWN_HOURS = 12


def _current_china_hour() -> str:
    # ad_hourly_detail.china_date 按 "%Y-%m-%d %H" 存(中国时区整点)
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H")


def _query_low_balance_accounts(hour: str) -> list[dict]:
    """campaign 级按户汇总指定部门 status=ACTIVE 系列的在投预算, account 级取余额,
    spend_d1 为昨日 account 级消耗(单位美元, 与"分"不同), 供计算充值目标。
    account_status=2(DISABLED,被停用)的户不预警。
    在投预算按单日限额封顶:account_dsl 取 Mongo 实时值(hourly 回填不及时),
    有正限额时取 min(系列预算, 限额×100), 空/0 按系列预算。
    余额低于封顶后预算 ALERT_BALANCE_RATIO 的拎出来。
    """
    dept_in = ", ".join(f"'{d}'" for d in DEPARTMENTS)
    day_1 = (
        datetime.strptime(hour[:10], "%Y-%m-%d") - timedelta(days=1)
    ).strftime("%Y-%m-%d")
    sql = f"""
        SELECT
            c.account_id,
            c.account_name,
            c.total_budget,
            a.balance,
            s.spend_d1
        FROM (
            SELECT account_id,
                   MAX(account_name) AS account_name,
                   SUM(cam_budget) AS total_budget
            FROM ad_hourly_detail
            WHERE china_date = '{hour}'
              AND level = 'campaign'
              AND status = 'ACTIVE'
              AND department IN ({dept_in})
            GROUP BY account_id
        ) c
        JOIN (
            SELECT account_id,
                   MAX(balance) AS balance
            FROM ad_hourly_detail
            WHERE china_date = '{hour}'
              AND level = 'account'
              AND (account_status <> 2 OR account_status IS NULL)
            GROUP BY account_id
        ) a ON c.account_id = a.account_id
        LEFT JOIN (
            SELECT account_id,
                   MAX(amount_spent) AS spend_d1
            FROM ad_daily_detail
            WHERE `date` = '{day_1}'
              AND level = 'account'
            GROUP BY account_id
        ) s ON c.account_id = s.account_id
        WHERE a.balance IS NOT NULL
        ORDER BY c.account_id
    """
    rows = mysql_client.read(sql)
    dsl_map = {
        str(d["_id"]): d.get("account_dsl")
        for d in mongo_client["fb_ad_accounts"].find(
            {"_id": {"$in": [str(r[0]) for r in rows]}},
            {"account_dsl": 1},
        )
    }
    result = []
    for account_id, account_name, total_budget, balance, spend_d1 in rows:
        dsl = float(dsl_map.get(str(account_id)) or 0)
        budget = float(total_budget)
        if dsl > 0:
            budget = min(budget, dsl * 100)
        if float(balance) < budget * ALERT_BALANCE_RATIO:
            result.append({
                "account_id": account_id,
                "account_name": account_name,
                "total_budget": budget,
                "balance": balance,
                "spend_d1": spend_d1,
                "account_dsl": dsl_map.get(str(account_id)),
            })
    return result


def _topup_amount(row: dict) -> int:
    """充值 = min(昨日消耗×倍数, 余额上限) − 余额, 向上取整到百位; 余额已够时为 0。
    余额上限: account_dsl 有值充到 account_dsl, null/0 按 DEFAULT_BALANCE_CAP。"""
    balance = float(row["balance"]) / 100
    spend_d1 = float(row["spend_d1"] or 0)
    dsl = float(row["account_dsl"] or 0)
    cap = dsl if dsl > 0 else DEFAULT_BALANCE_CAP
    gap = min(spend_d1 * GAP_SPEND_D1_MULTIPLIER, cap) - balance
    if gap <= 0:
        return 0
    return math.ceil(gap / 100) * 100


def _fetch_account_opened_ids(fb_account_ids: list[str]) -> dict[str, int]:
    """fb_account_id -> md_account_opened.id(即接口的 accountOpenedId), 已回收的不取。"""
    if not fb_account_ids:
        return {}
    in_clause = ", ".join(f"'{a}'" for a in fb_account_ids)
    rows = erp_db.read(
        "SELECT fb_account_id, id FROM md_account_opened "
        f"WHERE fb_account_id IN ({in_clause}) AND recycle_flag = 0"
    )
    return {str(fb): int(oid) for fb, oid in rows}


def _fetch_skip_recharge_accounts(fb_account_ids: list[str]) -> set[str]:
    """不该再提充值的 fb_account_id 集合: 有待审核充值单(audit_status=0),
    或 RECHARGE_COOLDOWN_HOURS 内提过充值申请(按 DB 时钟比 create_time)。"""
    if not fb_account_ids:
        return set()
    in_clause = ", ".join(f"'{a}'" for a in fb_account_ids)
    rows = erp_db.read(
        "SELECT DISTINCT fb_account_id FROM md_account_balance_record "
        f"WHERE fb_account_id IN ({in_clause}) AND change_type = 1 "
        "AND (audit_status = 0 "
        f"OR create_time >= NOW() - INTERVAL {RECHARGE_COOLDOWN_HOURS} HOUR)"
    )
    return {str(r[0]) for r in rows}


def _submit_recharge_applies(rows: list[dict]) -> None:
    if not md_open_api.SECRET_KEY or not md_open_api.USER_ID:
        logging.warning("充值申请：secretKey/userId 未配置, 跳过自动提交")
        return
    fb_ids = [str(r["account_id"]) for r in rows]
    opened_map = _fetch_account_opened_ids(fb_ids)
    skip = _fetch_skip_recharge_accounts(fb_ids)
    for row in rows:
        account_id = str(row["account_id"])
        if account_id in skip:
            logging.info(
                "充值申请：户 %s 已有待审核或 %s 小时内已提过充值单, 跳过",
                account_id, RECHARGE_COOLDOWN_HOURS,
            )
            continue
        opened_id = opened_map.get(account_id)
        if opened_id is None:
            logging.warning(
                "充值申请：户 %s 在 md_account_opened 无记录(或已回收), 跳过", account_id
            )
            continue
        amount = _topup_amount(row)
        detail = (
            f"户 {row['account_name']}({account_id}) openedId={opened_id} "
            f"余额 {float(row['balance']) / 100:.2f} "
            f"昨日消耗 {float(row['spend_d1'] or 0):.2f}×{GAP_SPEND_D1_MULTIPLIER} "
            f"dsl {row['account_dsl']}"
        )
        if amount <= 0:
            logging.info("充值申请：%s -> 余额已够, 无需充值", detail)
            continue
        try:
            md_open_api.recharge_apply(opened_id, amount)
            logging.info("充值申请：%s -> 已提交 %s", detail, amount)
        except Exception:
            logging.exception("充值申请：%s -> 提交 %s 失败", detail, amount)


def check_account_balance_alert() -> None:
    hour = _current_china_hour()
    rows = _query_low_balance_accounts(hour)
    if not rows:
        logging.info("账户余额预警：%s 无余额不足账户", hour)
        return
    _submit_recharge_applies(rows)
    logging.info("账户余额预警：命中 %s 个账户", len(rows))


if __name__ == "__main__":
    init("account balance alert")
    check_account_balance_alert()
