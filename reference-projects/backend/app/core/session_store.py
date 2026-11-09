"""服务端会话:状态存 Redis,客户端只持有 HttpOnly cookie 里的不透明 session_id。
登出 / 单点登出 = 直接删 Redis 记录,不再依赖无状态 token + 黑名单。"""
import json
import secrets
from typing import Optional

from fastapi import Response

from app.conf import Env, env
from app.db.async_redis import get_redis_cli

_redis = get_redis_cli(4)

COOKIE_NAME = "app_session"
SESSION_TTL = 7 * 24 * 3600

_SESS = "sess:"
_SID_INDEX = "sess_sid:"  # IdP sid -> {session_id...},单点登出时按 sid 批量删


async def create_session(user_id: str, idp_sid: Optional[str]) -> str:
    session_id = secrets.token_urlsafe(32)
    await _redis.set(_SESS + session_id, json.dumps({"user_id": user_id, "idp_sid": idp_sid}), ex=SESSION_TTL)
    if idp_sid:
        await _redis.sadd(_SID_INDEX + idp_sid, session_id)
        await _redis.expire(_SID_INDEX + idp_sid, SESSION_TTL)
    return session_id


async def get_session(session_id: str) -> Optional[dict]:
    raw = await _redis.get(_SESS + session_id)
    return json.loads(raw) if raw else None


async def delete_session(session_id: str) -> None:
    data = await get_session(session_id)
    await _redis.delete(_SESS + session_id)
    if data and data.get("idp_sid"):
        await _redis.srem(_SID_INDEX + data["idp_sid"], session_id)


async def delete_sessions_by_sid(idp_sid: str) -> int:
    """单点登出:删掉某 IdP 会话(sid)下的所有本地会话。"""
    key = _SID_INDEX + idp_sid
    session_ids = await _redis.smembers(key)
    if session_ids:
        await _redis.delete(*[_SESS + m for m in session_ids])
    await _redis.delete(key)
    return len(session_ids)


def set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        session_id,
        max_age=SESSION_TTL,
        httponly=True,
        secure=(env == Env.PROD),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")
