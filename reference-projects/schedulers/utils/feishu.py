# -*- coding: utf-8 -*-
import base64
import hashlib
import hmac
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests


FEISHU_APP_ID = "cli_aa9c2ebbc6799bd6"
FEISHU_APP_SECRET = "REDACTED_REFERENCE_SECRET"

PAY_ERROR_CHAT_ID = "oc_2d038e9df6bcc507fb60542c87029f09"  # 支付错误通知群
PAY_ERROR_TEST_CHAT_ID = "oc_2c8acef7a911bb8a6216bf1c4796eed4"  # 支付错误通知测试群
ACCOUNT_UNBIND_CHAT_ID = "oc_c0980681e954f819eda1071a84f0f534"  # ad系统户管账号授权掉绑通知群

BASE_URL = "https://open.feishu.cn/open-apis"
REQUEST_TIMEOUT = 15

_token_cache: dict = {"token": "", "expires_at": 0.0}
_app_token_caches: dict[str, dict] = {}


def get_feishu_tenant_access_token(app_id: str, app_secret: str) -> str | None:
    """按应用获取并缓存 tenant_access_token。"""
    cache = _app_token_caches.setdefault(app_id, {"token": "", "expires_at": 0.0})
    if cache["token"] and time.time() < cache["expires_at"]:
        return cache["token"]
    try:
        response = requests.post(
            f"{BASE_URL}/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=REQUEST_TIMEOUT,
        )
        data = response.json()
        if data.get("code") != 0:
            logging.error("飞书获取 tenant_access_token 失败, 响应=%s", response.text)
            return None
        # 提前 5 分钟刷新, 避免用到临期 token
        cache["token"] = data["tenant_access_token"]
        cache["expires_at"] = time.time() + data["expire"] - 300
        return cache["token"]
    except Exception:
        logging.exception("飞书获取 tenant_access_token 异常")
        return None


def _get_tenant_access_token() -> str | None:
    if _token_cache["token"] and time.time() < _token_cache["expires_at"]:
        return _token_cache["token"]
    token = get_feishu_tenant_access_token(FEISHU_APP_ID, FEISHU_APP_SECRET)
    if token:
        _token_cache["token"] = token
        _token_cache["expires_at"] = _app_token_caches[FEISHU_APP_ID]["expires_at"]
    return token


def send_feishu_msg(
    message: str,
    receive_id: str,
    receive_id_type: str = "chat_id",
):
    """receive_id_type: chat_id(群) / open_id / user_id / email"""
    text = (message or "").strip()
    if not text:
        return None
    token = _get_tenant_access_token()
    if not token:
        return None
    try:
        response = requests.post(
            f"{BASE_URL}/im/v1/messages",
            params={"receive_id_type": receive_id_type},
            headers={"Authorization": f"Bearer {token}"},
            json={
                "receive_id": receive_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
            timeout=REQUEST_TIMEOUT,
        )
        data = response.json()
        if data.get("code") != 0:
            logging.error(
                "飞书发送消息失败, receive_id=%s, 响应=%s", receive_id, response.text
            )
            return None
        return data
    except Exception:
        logging.exception("飞书发送消息异常, receive_id=%s", receive_id)
        return None


def send_feishu_card(
    card: dict,
    receive_id: str,
    receive_id_type: str = "chat_id",
):
    """发送交互卡片(消息卡片 JSON 1.0 结构)"""
    token = _get_tenant_access_token()
    if not token:
        return None
    try:
        response = requests.post(
            f"{BASE_URL}/im/v1/messages",
            params={"receive_id_type": receive_id_type},
            headers={"Authorization": f"Bearer {token}"},
            json={
                "receive_id": receive_id,
                "msg_type": "interactive",
                "content": json.dumps(card, ensure_ascii=False),
            },
            timeout=REQUEST_TIMEOUT,
        )
        data = response.json()
        if data.get("code") != 0:
            logging.error(
                "飞书发送卡片失败, receive_id=%s, 响应=%s", receive_id, response.text
            )
            return None
        return data
    except Exception:
        logging.exception("飞书发送卡片异常, receive_id=%s", receive_id)
        return None


def _upload_feishu_message_image(
    image: bytes,
    *,
    app_id: str,
    app_secret: str,
) -> str | None:
    """上传用于发送消息的图片，返回 image_key。"""
    if not image:
        return None
    token = get_feishu_tenant_access_token(app_id, app_secret)
    if not token:
        return None
    headers = {"Authorization": f"Bearer {token}"}
    try:
        upload_response = requests.post(
            f"{BASE_URL}/im/v1/images",
            headers=headers,
            data={"image_type": "message"},
            files={"image": ("report.png", image, "image/png")},
            timeout=REQUEST_TIMEOUT,
        )
        upload_data = upload_response.json()
        image_key = upload_data.get("data", {}).get("image_key")
        if upload_data.get("code") != 0 or not image_key:
            logging.error("飞书上传图片失败, 响应=%s", upload_response.text)
            return None
        return image_key
    except Exception:
        logging.exception("飞书上传图片异常")
        return None


def send_feishu_image(
    image: bytes,
    receive_id: str = "",
    *,
    app_id: str = FEISHU_APP_ID,
    app_secret: str = FEISHU_APP_SECRET,
    receive_id_type: str = "chat_id",
    target: str = "production",
    webhook_url: str = "",
    webhook_secret: str = "",
):
    """上传图片后发送。

    target="production" 通过飞书应用向 receive_id 发送；target="test" 时发送到
    指定的签名 Webhook，仍使用 app_id/app_secret 上传图片以获得 image_key。
    """
    if target not in {"production", "test"}:
        raise ValueError(f"未知飞书图片发送目标: {target}")
    if target == "production" and not receive_id:
        return None
    if target == "test" and not webhook_url:
        logging.error("飞书测试机器人缺少 webhook_url")
        return None

    image_key = _upload_feishu_message_image(
        image, app_id=app_id, app_secret=app_secret
    )
    if not image_key:
        return None

    if target == "test":
        return _send_feishu_bot_webhook_payload(
            webhook_url,
            {"msg_type": "image", "content": {"image_key": image_key}},
            webhook_secret,
        )

    token = get_feishu_tenant_access_token(app_id, app_secret)
    if not token:
        return None
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.post(
            f"{BASE_URL}/im/v1/messages",
            params={"receive_id_type": receive_id_type},
            headers=headers,
            json={
                "receive_id": receive_id,
                "msg_type": "image",
                "content": json.dumps({"image_key": image_key}),
            },
            timeout=REQUEST_TIMEOUT,
        )
        data = response.json()
        if data.get("code") != 0:
            logging.error("飞书发送图片失败, receive_id=%s, 响应=%s", receive_id, response.text)
            return None
        return data
    except Exception:
        logging.exception("飞书上传或发送图片异常, receive_id=%s", receive_id)
        return None


def get_feishu_open_ids_by_mobiles(
    mobiles: list[str],
    *,
    app_id: str = FEISHU_APP_ID,
    app_secret: str = FEISHU_APP_SECRET,
) -> dict[str, str]:
    """手机号 -> open_id，查不到的手机号不出现在返回里。

    需要应用具备 contact:user.id:readonly 权限。飞书回显的手机号可能带区号(+86)，
    额外用后 11 位再存一份，调用方传裸号也能取到。
    """
    token = get_feishu_tenant_access_token(app_id, app_secret)
    if not token:
        return {}
    result: dict[str, str] = {}
    for start in range(0, len(mobiles), 50):  # 单次最多 50 个
        chunk = mobiles[start:start + 50]
        try:
            response = requests.post(
                f"{BASE_URL}/contact/v3/users/batch_get_id",
                params={"user_id_type": "open_id"},
                headers={"Authorization": f"Bearer {token}"},
                json={"mobiles": chunk},
                timeout=REQUEST_TIMEOUT,
            )
            data = response.json()
            if data.get("code") != 0:
                logging.error("飞书手机号查 open_id 失败, 响应=%s", response.text)
                continue
            for item in data.get("data", {}).get("user_list", []):
                open_id = item.get("user_id")
                mobile = str(item.get("mobile") or "")
                if not open_id or not mobile:
                    continue
                result[mobile] = open_id
                digits = "".join(c for c in mobile if c.isdigit())
                if len(digits) >= 11:
                    result[digits[-11:]] = open_id
        except Exception:
            logging.exception("飞书手机号查 open_id 异常")
    return result


def send_feishu_file(
    file_bytes: bytes,
    file_name: str,
    receive_id: str,
    *,
    app_id: str = FEISHU_APP_ID,
    app_secret: str = FEISHU_APP_SECRET,
    receive_id_type: str = "open_id",
    file_type: str = "stream",
):
    """上传文件后发送。xlsx 等非飞书内置类型用 file_type='stream'。"""
    if not file_bytes or not receive_id:
        return None
    token = get_feishu_tenant_access_token(app_id, app_secret)
    if not token:
        return None
    headers = {"Authorization": f"Bearer {token}"}
    try:
        upload_response = requests.post(
            f"{BASE_URL}/im/v1/files",
            headers=headers,
            data={"file_type": file_type, "file_name": file_name},
            files={"file": (file_name, file_bytes)},
            timeout=REQUEST_TIMEOUT,
        )
        upload_data = upload_response.json()
        file_key = upload_data.get("data", {}).get("file_key")
        if upload_data.get("code") != 0 or not file_key:
            logging.error("飞书上传文件失败, file_name=%s, 响应=%s", file_name, upload_response.text)
            return None
        response = requests.post(
            f"{BASE_URL}/im/v1/messages",
            params={"receive_id_type": receive_id_type},
            headers=headers,
            json={
                "receive_id": receive_id,
                "msg_type": "file",
                "content": json.dumps({"file_key": file_key}),
            },
            timeout=REQUEST_TIMEOUT,
        )
        data = response.json()
        if data.get("code") != 0:
            logging.error("飞书发送文件失败, receive_id=%s, 响应=%s", receive_id, response.text)
            return None
        return data
    except Exception:
        logging.exception("飞书上传或发送文件异常, receive_id=%s", receive_id)
        return None


def send_feishu_msg_backend(
    message: str,
    receive_id: str,
    receive_id_type: str = "chat_id",
):
    thread = threading.Thread(
        target=send_feishu_msg, args=(message, receive_id, receive_id_type)
    )
    thread.daemon = True
    thread.start()


def _gen_bot_sign(timestamp: int, secret: str) -> str:
    # 飞书机器人签名: 以 "{timestamp}\n{secret}" 为 key 对空内容做 HMAC-SHA256, 再 base64
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def _send_feishu_bot_webhook_payload(webhook_url: str, body: dict, secret: str = ""):
    """发送自定义机器人消息体；secret 非空时附加签名。"""
    if not webhook_url:
        return None
    body = body.copy()
    if secret:
        timestamp = int(time.time())
        body["timestamp"] = str(timestamp)
        body["sign"] = _gen_bot_sign(timestamp, secret)
    try:
        response = requests.post(
            webhook_url,
            json=body,
            timeout=REQUEST_TIMEOUT,
        )
        data = response.json()
        # 新版返回 code=0, 老版返回 StatusCode=0
        if data.get("code") == 0 or data.get("StatusCode") == 0:
            return data
        logging.error("飞书群机器人发送失败, 响应=%s", response.text)
        return None
    except Exception:
        logging.exception("飞书群机器人发送异常")
        return None


def send_feishu_bot_webhook(webhook_url: str, message: str, secret: str = ""):
    """群机器人 webhook 发纯文本(secret 非空时带签名, 无需 tenant_access_token)"""
    text = (message or "").strip()
    if not text:
        return None
    return _send_feishu_bot_webhook_payload(
        webhook_url,
        {"msg_type": "text", "content": {"text": text}},
        secret,
    )


# ---------------- 电子表格(Spreadsheet)读取 ----------------

_SHEET_TIMEOUT = 30
_SHEET_BATCH_ROWS = 500  # 单次 values 接口读取的行数
_CST = timezone(timedelta(hours=8))
# Excel 1900 日期系统基准日。带上 CST:表格里填的是中国日期,
# 返回 naive 会被 pymongo 当 UTC 存,读回来平白多 8 小时。
_EXCEL_EPOCH = datetime(1899, 12, 30, tzinfo=_CST)


def _require_tenant_access_token(app_id: str, app_secret: str) -> str:
    token = get_feishu_tenant_access_token(app_id, app_secret)
    if not token:
        raise RuntimeError(f"飞书获取 tenant_access_token 失败, app_id={app_id}")
    return token


def _feishu_get(path: str, token: str, params: dict = None, timeout: int = REQUEST_TIMEOUT) -> dict:
    """调飞书接口取 data。code!=0 抛异常——同步场景静默返回空会被当成"同步了 0 条"。"""
    response = requests.get(
        f"{BASE_URL}{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=timeout,
    )
    data = response.json()
    if data.get("code") != 0:
        raise RuntimeError(f"飞书接口 {path} 调用失败, 响应={response.text}")
    return data.get("data") or {}


def flatten_cell(value):
    """单元格可能是富文本/超链接的段数组(如邮箱列),展平取纯文本;空串归一成 None。"""
    if isinstance(value, list):
        text = "".join(str(seg.get("text") or "") for seg in value if isinstance(seg, dict))
        return text.strip() or None
    if isinstance(value, str):
        return value.strip() or None
    return value


def sheet_value_to_datetime(value):
    """表格日期单元格转 datetime。

    日期列读出来是 Excel 1900 序列号(45918 → 2025-09-18)而不是日期串;
    数值过大时按秒/毫秒时间戳处理。识别不了返回 None。返回值带 CST 时区。
    """
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    if value < 60000:
        return _EXCEL_EPOCH + timedelta(days=value)
    return datetime.fromtimestamp(value / 1000 if value >= 100_000_000_000 else value, _CST)


def resolve_spreadsheet_token(url_or_token: str, *, app_id: str, app_secret: str) -> str:
    """把电子表格 URL 解析成 sheets 接口要的 spreadsheet_token;传入的不是 URL 时原样返回。

    知识库链接(/wiki/)上带的是节点 token,跟文档 token 不是一个值,必须换成 obj_token。
    """
    value = (url_or_token or "").strip()
    if not value:
        raise ValueError("电子表格 token 或 URL 不能为空")
    if not value.startswith("http"):
        return value
    for marker in ("/sheets/", "/wiki/"):
        if marker not in value:
            continue
        node = value.split(marker, 1)[1].split("?")[0].split("/")[0]
        if marker == "/sheets/":
            return node
        token = _require_tenant_access_token(app_id, app_secret)
        node_info = _feishu_get("/wiki/v2/spaces/get_node", token, {"token": node}).get("node") or {}
        obj_token = node_info.get("obj_token")
        if not obj_token:
            raise RuntimeError(f"知识库节点未返回 obj_token: {url_or_token}")
        return obj_token
    raise ValueError(f"无法从 URL 提取电子表格 token: {url_or_token}")


def list_sheets(spreadsheet_token: str, *, app_id: str, app_secret: str) -> list[dict]:
    """工作表列表,每项含 sheet_id / title / row_count / column_count。"""
    token = _require_tenant_access_token(app_id, app_secret)
    data = _feishu_get(f"/sheets/v2/spreadsheets/{spreadsheet_token}/metainfo", token)
    return [
        {
            "sheet_id": sheet["sheetId"],
            "title": sheet["title"],
            "row_count": sheet["rowCount"],
            "column_count": sheet["columnCount"],
        }
        for sheet in data.get("sheets") or []
    ]


def _column_letter(index: int) -> str:
    """列序号转字母: 1 → A, 27 → AA。"""
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def _dedupe_headers(cells: list) -> list[str]:
    """同名列从第二次出现起加 #2/#3 后缀,否则后列会覆盖前列(渠道充值账户有两个"备注")。"""
    headers, seen = [], {}
    for cell in cells:
        name = str(flatten_cell(cell) or "")
        if not name:
            headers.append("")
            continue
        seen[name] = seen.get(name, 0) + 1
        headers.append(name if seen[name] == 1 else f"{name}#{seen[name]}")
    return headers


def read_sheet_rows(
    spreadsheet_token: str,
    sheet_id: str,
    *,
    app_id: str,
    app_secret: str,
    row_count: int,
    column_count: int,
) -> list[dict]:
    """整表读取,返回 [{列名: 值}],全空行已滤掉,工作表行号放在 _row。

    有表头的列始终保留键，行尾空单元格补 None，以区分空值与整张表缺列。

    Sheets 接口没有游标分页,只能按行区间分批读。row_count 是表格声明的行数,
    通常远大于真实数据行(GC企业户声明 9582 行,末尾大片是空行),所以靠空行过滤收尾。
    """
    token = _require_tenant_access_token(app_id, app_secret)
    end_col = _column_letter(column_count)
    base = f"/sheets/v2/spreadsheets/{spreadsheet_token}/values"

    def _values(cell_range: str) -> list:
        data = _feishu_get(f"{base}/{quote(cell_range, safe='')}", token, timeout=_SHEET_TIMEOUT)
        return (data.get("valueRange") or {}).get("values") or []

    header_values = _values(f"{sheet_id}!A1:{end_col}1")
    headers = _dedupe_headers(header_values[0] if header_values else [])

    rows = []
    for start in range(2, row_count + 1, _SHEET_BATCH_ROWS):
        stop = min(start + _SHEET_BATCH_ROWS - 1, row_count)
        for offset, raw in enumerate(_values(f"{sheet_id}!A{start}:{end_col}{stop}")):
            cells = [flatten_cell(cell) for cell in raw]
            if all(cell is None for cell in cells):
                continue
            row = {"_row": start + offset}
            row.update({
                name: cells[index] if index < len(cells) else None
                for index, name in enumerate(headers)
                if name
            })
            rows.append(row)
    return rows


if __name__ == "__main__":
    send_feishu_msg("测试消息", PAY_ERROR_TEST_CHAT_ID)
