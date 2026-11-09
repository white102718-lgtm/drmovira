"""飞书通知：tenant_access_token 缓存于 redis、手机号换 open_id 缓存于 mongo user.feishu_id、发文本消息。

所有对外调用失败均吞异常+记日志、返回 None/False，调用方（通知）不因飞书故障受影响。
"""

import json
import logging
from typing import Optional, Any

import aiohttp

from app.db.clients import redis_cli, erp_db
from app.db.mongo import user_cols
from env_vault.env_conf import env, Env

# 飞书自建应用凭据
APP_ID = "cli_aab8e929373cdbfc"
APP_SECRET = "REDACTED_REFERENCE_SECRET"

BASE_URL = "https://open.feishu.cn/open-apis"
TOKEN_REDIS_KEY = "feishu:tenant_access_token"
TOKEN_TTL_SAFE_GAP = 300  # 提前 5 分钟过期，避免边界拿到将失效的 token
REQUEST_TIMEOUT = 15

# 素材中台通知群 chat_id
MATERIAL_GROUP_CHAT_ID = "oc_d1e472f00ea8d8c99abb04b199eafdb9"


async def _post(
    url: str, payload: dict, headers: Optional[dict] = None
) -> Optional[dict[str, Any]]:
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                data = await resp.json()
    except Exception:
        logging.exception("飞书 API 调用异常 url=%s", url)
        return None
    if data.get("code") != 0:
        logging.error("飞书 API 返回错误 url=%s resp=%s", url, data)
        return None
    return data


async def get_tenant_access_token() -> Optional[str]:
    token = await redis_cli.get(TOKEN_REDIS_KEY)
    if token:
        return token
    data = await _post(
        f"{BASE_URL}/auth/v3/tenant_access_token/internal",
        {"app_id": APP_ID, "app_secret": APP_SECRET},
    )
    if not data:
        return None
    token = data["tenant_access_token"]
    ttl = max(data.get("expire", 7200) - TOKEN_TTL_SAFE_GAP, 60)
    await redis_cli.setex(TOKEN_REDIS_KEY, ttl, token)
    return token


async def _mobile_to_open_id(token: str, mobile: str) -> Optional[str]:
    data = await _post(
        f"{BASE_URL}/contact/v3/users/batch_get_id?user_id_type=open_id",
        {"mobiles": [mobile]},
        headers={"Authorization": f"Bearer {token}"},
    )
    if not data:
        return None
    for u in (data.get("data") or {}).get("user_list") or []:
        if u.get("user_id"):
            return u["user_id"]
    logging.warning("飞书: 手机号 %s 未匹配到用户", mobile)
    return None


async def get_open_id(user_doc: dict) -> Optional[str]:
    """取素材师 open_id：mongo user.feishu_id 命中即用；否则按 user_name 查 ERP feishu_account 换取并回写。"""
    if user_doc.get("feishu_id"):
        return user_doc["feishu_id"]
    full_name = user_doc.get("full_name")
    if not full_name:
        return None
    row = await erp_db.fetchone(
        "SELECT feishu_account FROM sys_user WHERE nick_name=%s AND status=0",
        (full_name,),
        as_dict=True,
    )
    mobile = row and row.get("feishu_account")
    if not mobile:
        logging.warning("飞书: nick_name=%s 未查到 feishu_account", full_name)
        return None
    token = await get_tenant_access_token()
    if not token:
        return None
    open_id = await _mobile_to_open_id(token, mobile)
    if not open_id:
        return None
    await user_cols.user.update_one(
        {"_id": user_doc["_id"]}, {"$set": {"feishu_id": open_id}}
    )
    return open_id


async def _send_text(receive_id_type: str, receive_id: str, text: str) -> bool:
    if env != Env.PROD:
        return True
    token = await get_tenant_access_token()
    if not token:
        return False
    data = await _post(
        f"{BASE_URL}/im/v1/messages?receive_id_type={receive_id_type}",
        {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    return bool(data)


async def send_text(open_id: str, text: str) -> bool:
    return await _send_text("open_id", open_id, text)


async def send_text_to_chat(chat_id: str, text: str) -> bool:
    return await _send_text("chat_id", chat_id, text)


async def notify_by_full_name(full_name: str, text: str) -> None:
    user = await user_cols.user.find_one({"full_name": full_name})
    if not user:
        logging.warning("飞书通知: 未找到用户 full_name=%s", full_name)
        return
    open_id = await get_open_id(user)
    if open_id:
        await send_text(open_id, text)
