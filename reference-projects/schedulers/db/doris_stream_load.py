"""Doris Stream Load(JSON 格式)写入。

直连 BE 8040 端口,避免 FE 重定向丢 BasicAuth。partial=True 走 Unique Key
部分列更新(只更新 columns 指定的列,其余列保留),等价于
`SET enable_unique_key_partial_update = true`。columns 必须含全部主键列。

flexible=True 走 flexible partial update(Doris >= 3.1):每行 JSON 各自决定
更新哪些列,行里没出现的列保留旧值,不传 columns。要求目标表
ALTER TABLE ... ENABLE FEATURE "UPDATE_FLEXIBLE_COLUMNS" 且为 MoW Unique 表。
"""

import json
import logging
import uuid
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

from conf import DorisConf

BE_HTTP_PORT = 8040


def stream_load(
    table: str,
    rows: list[dict],
    columns: list[str] | None = None,
    partial: bool = True,
    database: str = "ad",
    host: str | None = None,
    user: str | None = None,
    password: str | None = None,
    flexible: bool = False,
) -> None:
    if not rows:
        return
    host = host or DorisConf.HOST
    user = user or DorisConf.USER
    password = password or DorisConf.PASSWORD
    url = f"http://{host}:{BE_HTTP_PORT}/api/{database}/{table}/_stream_load"
    headers = {
        "Expect": "100-continue",
        "format": "json",
        "strip_outer_array": "true",
        "label": f"{table}_{uuid.uuid4().hex}",
    }
    if flexible:
        # flexible 模式禁止传 columns / partial_columns 等 header
        headers["unique_key_update_mode"] = "UPDATE_FLEXIBLE_COLUMNS"
    else:
        headers["columns"] = ",".join(columns)
        if partial:
            headers["partial_columns"] = "true"
    resp = requests.put(
        url,
        data=json.dumps(rows, default=str).encode("utf-8"),
        headers=headers,
        auth=HTTPBasicAuth(user, password),
        timeout=300,
    )
    resp.raise_for_status()
    result = resp.json()
    if result.get("Status") not in ("Success", "Publish Timeout"):
        dump = Path(__file__).parent.parent / "logs" / f"stream_load_fail_{headers['label']}.json"
        dump.write_text(json.dumps(rows, default=str, ensure_ascii=False), encoding="utf-8")
        raise RuntimeError(f"Stream Load 失败 {table} (payload已存 {dump.name}): {result}")
    logging.info(
        f"Stream Load {table}: {result.get('Status')} "
        f"NumberLoadedRows={result.get('NumberLoadedRows')}"
    )
