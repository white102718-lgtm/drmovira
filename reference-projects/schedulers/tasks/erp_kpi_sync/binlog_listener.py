# -*- coding:utf-8 -*-
"""ERP binlog 实时监听: 订阅 fbad-suger 库 fbad_ad_task / fbad_ad_subtask / task_kpi_info
的行事件,取出受影响的 task_id,调 sync_erp_kpi_to_mongo(task_ids) 走既有同步逻辑。

- 位点存 redis,重启续读;位点已被服务端清理(1236)时从最新位置重新开始。
- 监听中断产生空窗时手动补: python -m tasks.erp_kpi_sync.erp_kpi_sync(同步近 30 分钟更新)。
"""
import json
import logging
import time

from pymysql.err import OperationalError
from pymysqlreplication import BinLogStreamReader
from pymysqlreplication.row_event import DeleteRowsEvent, UpdateRowsEvent, WriteRowsEvent

from conf import ErpMySQLConf
from db.clients import redis_cli
from tasks.erp_kpi_sync.erp_kpi_sync import sync_erp_kpi_to_mongo

_TABLES = ["fbad_ad_task", "fbad_ad_subtask", "task_kpi_info"]
_POS_KEY = "erp_kpi_binlog:pos"
_SERVER_ID = 4001  # 伪装从库的唯一 id,不能与 ERP MySQL 的 server_id 及其他副本重复
_IDLE_SLEEP = 2  # 追平后的轮询间隔
_FLUSH_INTERVAL = 3  # 事件攒批窗口;流量大时流读不到 EOF,必须边读边按时间窗 flush


def _load_pos():
    raw = redis_cli.get(_POS_KEY)
    if not raw:
        return None, None
    pos = json.loads(raw)
    return pos["file"], pos["pos"]


def _save_pos(log_file, log_pos):
    redis_cli.set(_POS_KEY, json.dumps({"file": log_file, "pos": log_pos}))


def _event_task_ids(event):
    ids = set()
    for row in event.rows:
        for values in (row.get("values"), row.get("after_values")):
            if values and values.get("task_id") is not None:
                ids.add(str(values["task_id"]))
    return ids


def _new_stream(log_file, log_pos):
    # resume_stream 必须为 True:False 会从 binlog 文件开头(pos 4)整文件重放。
    # 无位点时传 None,库会取 master 当前位置,即"从最新开始"。
    return BinLogStreamReader(
        connection_settings={
            "host": ErpMySQLConf.HOST,
            "port": ErpMySQLConf.PORT,
            "user": ErpMySQLConf.USER,
            "passwd": ErpMySQLConf.PASSWORD,
        },
        server_id=_SERVER_ID,
        only_schemas=[ErpMySQLConf.DATABASE],
        only_tables=_TABLES,
        only_events=[WriteRowsEvent, UpdateRowsEvent, DeleteRowsEvent],
        log_file=log_file,
        log_pos=log_pos,
        resume_stream=True,
        blocking=False,  # 追平即返回 None,外层攒批 + 休眠轮询
    )


def _flush(stream, task_ids):
    """有变更就同步,并保存当前位点;位点在同步成功后才存,崩溃时重放(幂等)。"""
    if task_ids:
        logging.info(f"binlog 捕获变更 task_ids={sorted(task_ids)}")
        sync_erp_kpi_to_mongo(task_ids=sorted(task_ids))
        task_ids.clear()
    if stream.log_file and stream.log_pos:
        _save_pos(stream.log_file, stream.log_pos)


def run():
    log_file, log_pos = _load_pos()
    logging.info(f"binlog 监听启动: 位点={log_file}:{log_pos}(None=从最新开始)")
    stream = _new_stream(log_file, log_pos)

    while True:
        try:
            task_ids = set()
            last_flush = time.monotonic()
            for event in stream:
                task_ids |= _event_task_ids(event)
                if time.monotonic() - last_flush >= _FLUSH_INTERVAL:
                    _flush(stream, task_ids)
                    last_flush = time.monotonic()
            _flush(stream, task_ids)  # 追平(EOF)后清掉剩余
        except OperationalError as e:
            if e.args and e.args[0] == 1236:  # 位点已被服务端清理
                logging.warning(f"binlog 位点失效,从最新位置重新监听,空窗需手动跑 erp_kpi_sync 补: {e}")
                redis_cli.delete(_POS_KEY)
                stream.close()
                stream = _new_stream(None, None)
            else:
                logging.exception("binlog 读取失败,10s 后重连")
                stream.close()
                time.sleep(10)
                stream = _new_stream(*_load_pos())
        time.sleep(_IDLE_SLEEP)


if __name__ == "__main__":
    from conf.log_conf import init

    init("erp_binlog_listener")
    run()
