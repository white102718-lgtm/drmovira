"""Doris 写入工具 —— 移植自 tasks/ad_sync/base_sync.py,字段语义、partial
update 行为、表名全部跟老 consumer 对齐(同一张表 `ad_daily_detail` +
`ad_hourly_detail`),保证新老 consumer 共写不冲突。

跟老 base_sync.py 的区别:
  - 拆成模块级函数,不挂在 BaseAdSync 上(`ad_sync_new` 不复用老类)
  - import 路径用 db.* / utils.* (这些是公共底层,可以引用)
  - 行为完全等价,粒度也保持 (ad_hourly_detail + ad_daily_detail 双写)
"""

import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List

from db.doris_stream_load import stream_load
from env_vault.env_conf import DorisConfNew
from utils.common_util import handle_error


logger = logging.getLogger(__name__)

HALF_HOUR_TABLE = "ad_half_hour_detail"


# 由独立的回填任务负责(backfill_ad_fields / backfill_agent_line_by_url /
# ad_materials_sync.reuse_historical_unique_names),consumer 不主动用全行
# upsert 写它们,避免把回填好的值覆盖回 NULL。
BACKFILL_MANAGED_COLUMNS = {
    "agent_line",
    "placer_id",
    "department",
    "game_platform",
    "landing_url",
    "unique_name",
}

# ad_daily_detail / ad_hourly_detail 的 UNIQUE KEY,partial update 必须始终带上
UK_COLUMNS = [
    "date",
    "ad_platform",
    "timezone_name",
    "account_id",
    "campaign_id",
    "ad_set_id",
    "ad_id",
]


def _convert_date_for_daily(data: List[Dict]) -> List[Dict]:
    """处理 daily 表的 date 字段(入参须是 hourly 视图,即 :30 首轮已挪到 " 01"):
      - "YYYY-MM-DD 00" → "YYYY-MM-(DD-1)"(本地 00:00 档 / review 拉的都是前一天)
      - 其它情况只取日期部分
    """
    daily_data: List[Dict] = []
    for record in data:
        new_record = record.copy()
        date_value = new_record.get("date", "")
        if date_value:
            if date_value.endswith(" 00"):
                date_part = date_value.split(" ")[0]
                prev_date = datetime.strptime(date_part, "%Y-%m-%d") - timedelta(days=1)
                new_record["date"] = prev_date.strftime("%Y-%m-%d")
            else:
                new_record["date"] = date_value.split(" ")[0]
        daily_data.append(new_record)
    return daily_data


def _convert_date_for_half_hour(data: List[Dict]) -> List[Dict]:
    """half 表直接用行里的精确半点时刻(transform 产出 "YYYY-MM-DD HH:MM"),
    只补秒段成 "YYYY-MM-DD HH:MM:00"。date/china_date 都是各自时区的真实半点,
    不再拼槽后缀 —— 半小时时区下"中国小时 + 本地分钟"的拼法两边都会错半小时。
    """
    half_data: List[Dict] = []
    for record in data:
        new_record = record.copy()
        if new_record.get("date"):
            new_record["date"] = f"{new_record['date']}:00"
        if new_record.get("china_date"):
            new_record["china_date"] = f"{new_record['china_date']}:00"
        half_data.append(new_record)
    return half_data


def _convert_date_for_hourly(data: List[Dict]) -> List[Dict]:
    """hourly 视图:date/china_date 从精确半点截到小时("YYYY-MM-DD HH")。
    特例:本地 00:30(当天首 30 分钟)挪到 " 01"(稍后被 01:00/01:30 轮同 UK
    覆盖精化):" 00" 槽留给 00:00 档的昨天定稿,daily 的「" 00" 行减一天」
    归属规则也因此保持不变。"""
    out: List[Dict] = []
    for record in data:
        new_record = record.copy()
        v = new_record.get("date")
        if v:
            day, hm = v.split(" ")
            new_record["date"] = f"{day} 01" if hm == "00:30" else f"{day} {hm[:2]}"
        cv = new_record.get("china_date")
        if cv:
            new_record["china_date"] = cv.split(":")[0]
        out.append(new_record)
    return out


def _write_table(table: str, data: List[Dict]) -> None:
    """以 flexible partial update 依次写主、副 Doris:
      - 非 BACKFILL_MANAGED_COLUMNS 的列每次都覆盖(指标/维度需要刷新)
      - BACKFILL_MANAGED_COLUMNS 中值为 None 的列从行里剔除不写入,
        flexible 模式下行里没出现的列保留旧值(backfill 已写好的值)
      - 主库写入成功后才写副库；副库失败会抛出，沿用上层的失败文件和告警日志
    """
    payload = [
        {k: v for k, v in row.items() if not (k in BACKFILL_MANAGED_COLUMNS and v is None)}
        for row in data
    ]
    stream_load(table, payload, flexible=True)
    try:
        stream_load(
            table,
            payload,
            host=DorisConfNew.HOST,
            user=DorisConfNew.USER,
            password=DorisConfNew.PASSWORD,
            flexible=True,
        )
    except Exception:
        logger.exception("[doris_writer] 副 Doris 写入失败 table=%s rows=%d", table, len(payload))
        raise


@handle_error(error_message="写入 Doris 失败", reraise=True)
def write_to_doris(data: List[Dict]) -> None:
    """写 doris 三张表,行里的 date/china_date 是精确半点(transform 产出),
    按各自粒度派生:
      1) ad_hourly_detail    —— 截到小时 "YYYY-MM-DD HH"(00:30 挪到 " 01",`_convert_date_for_hourly`)
      2) ad_daily_detail     —— 日粒度,从 hourly 视图派生 (`_convert_date_for_daily`)
      3) ad_half_hour_detail —— 精确半点原样落库 (`_convert_date_for_half_hour`)

    走 stream load flexible partial update(HTTP 直连 BE),每表一次导入,
    不占 Doris 的 mysql 连接。
    """
    if not data:
        logger.info("[doris_writer] 没有数据需要写入 Doris")
        return

    hourly = _convert_date_for_hourly(data)
    _write_table("ad_hourly_detail", hourly)
    _write_table("ad_daily_detail", _convert_date_for_daily(hourly))
    _write_table(HALF_HOUR_TABLE, _convert_date_for_half_hour(data))

    logger.info("[doris_writer] 成功写入 %d 条数据", len(data))


class _DorisBatchWriter:
    """进程级 stream load 攒批:account 子线程各自 enqueue,单个后台线程把
    两张表各自合并成大批次串行写。把"每户一次、几十路并发的小导入"压成"几秒
    一次的串行大导入",避免单机 BE 版本堆积 + 并发打满(实测 BE 8 核 / 热点
    tablet 版本 200+ / streaming_load 并发 78 导致 stream load 300s 超时)。
    """

    FLUSH_ROWS = 10000         # 任一表攒够即触发刷
    FLUSH_INTERVAL_SEC = 30.0  # 后台兜底刷间隔(攒不满时最多滞留这么久)

    def __init__(self) -> None:
        self._buf: Dict[str, List[Dict]] = {
            HALF_HOUR_TABLE: [],
            "ad_hourly_detail": [],
            "ad_daily_detail": [],
        }
        self._cv = threading.Condition()
        self._flusher_started = False

    def _ensure_flusher(self) -> None:
        if self._flusher_started:
            return
        with self._cv:
            if not self._flusher_started:
                threading.Thread(target=self._loop, name="doris-flush", daemon=True).start()
                self._flusher_started = True

    def enqueue(self, data: List[Dict]) -> None:
        if not data:
            return
        # 三张表的视图都在入队此刻从行内精确半点派生,不受后台攒批延迟影响
        hourly = _convert_date_for_hourly(data)
        daily = _convert_date_for_daily(hourly)
        half = _convert_date_for_half_hour(data)
        self._ensure_flusher()
        with self._cv:
            self._buf["ad_hourly_detail"].extend(hourly)
            self._buf["ad_daily_detail"].extend(daily)
            self._buf[HALF_HOUR_TABLE].extend(half)
            if any(len(rows) >= self.FLUSH_ROWS for rows in self._buf.values()):
                self._cv.notify()

    def _loop(self) -> None:
        while True:
            with self._cv:
                self._cv.wait(timeout=self.FLUSH_INTERVAL_SEC)
            self.flush()

    def flush(self) -> None:
        with self._cv:
            pending = [(t, rows) for t, rows in self._buf.items() if rows]
            for t, _ in pending:
                self._buf[t] = []
        for table, rows in pending:
            try:
                _write_table(table, rows)
            except Exception:
                # 丢这批不重入队:下一次 hourly/review 用同 UK 覆盖刷新即可;重入队会在
                # BE 持续故障时撑爆内存。stream_load 失败时已把 payload dump 到文件。
                logger.exception("[doris_writer] 批量刷写失败,丢弃 table=%s rows=%d", table, len(rows))


_batch_writer = _DorisBatchWriter()


def enqueue_to_doris(data: List[Dict]) -> None:
    """高并发 consumer 用:行攒进进程级 buffer,后台线程合并成大批次写。
    入队即返回,不等真正落库 —— 落库成败跟单户成败解耦(失败见 flush 日志)。"""
    _batch_writer.enqueue(data)


def flush_doris() -> None:
    """把 buffer 剩余行立刻刷出。worker 抽干/退出时调,避免尾批滞留。"""
    _batch_writer.flush()
