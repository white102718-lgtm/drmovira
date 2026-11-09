import base64
import hashlib
import logging
import re
import secrets
import time
from typing import Optional
from urllib.parse import urlencode

import aiohttp
from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from jose import JWTError, jwt

from app.conf import IdpConf
from app.conf.api_conf import (
    idp_issuer,
    idp_client_id,
    idp_redirect_uri,
    idp_frontend_landing,
)
from app.core.security import public
from app.core.session_store import (
    COOKIE_NAME,
    clear_session_cookie,
    create_session,
    delete_session,
    delete_sessions_by_sid,
    set_session_cookie,
)
from app.db.mongo import user_cols

_BACKCHANNEL_LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"

router = APIRouter(prefix="/auth/oauth", tags=["auth"])

_jwks_cache: dict = {"jwks": None, "fetched_at": 0.0}
_JWKS_TTL = 3600


async def _get_jwks() -> dict:
    if not _jwks_cache["jwks"] or time.time() - _jwks_cache["fetched_at"] > _JWKS_TTL:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.get(f"{idp_issuer.rstrip('/')}/oauth/jwks") as r:
                r.raise_for_status()
                _jwks_cache["jwks"] = await r.json()
                _jwks_cache["fetched_at"] = time.time()
    return _jwks_cache["jwks"]


def _make_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


# 本地/内网调试:localhost 或 192.168.x.x 的 5555 端口前端,登录后跳回它自己。
# 回调地址还必须逐个登记到 auth-server 的 client.redirect_uris,否则被 IdP 拒。
_DEV_ORIGIN_RE = re.compile(r"^http://(localhost|192\.168\.\d{1,3}\.\d{1,3}):5555$")


def _resolve_route(return_to: Optional[str]) -> tuple[str, str]:
    if return_to and _DEV_ORIGIN_RE.match(return_to):
        return f"{return_to}/backend/auth/oauth/callback", f"{return_to}/oauth-landing"
    return idp_redirect_uri, idp_frontend_landing


@router.get("/login")
@public
async def oauth_login(request: Request):
    state = secrets.token_urlsafe(16)
    verifier, challenge = _make_pkce_pair()
    extra = dict(request.query_params)
    redirect_uri, landing = _resolve_route(extra.pop("return_to", None))
    request.session["oauth_state"] = state
    request.session["pkce_verifier"] = verifier
    request.session["oauth_extra"] = extra
    request.session["oauth_redirect_uri"] = redirect_uri
    request.session["oauth_landing"] = landing
    params = {
        "client_id": idp_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid profile phone",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return RedirectResponse(f"{idp_issuer.rstrip('/')}/oauth/authorize?{urlencode(params)}")


@router.get("/callback")
@public
async def oauth_callback(request: Request, code: str, state: Optional[str] = None):
    saved = request.session.pop("oauth_state", None)
    verifier = request.session.pop("pkce_verifier", None)
    extra = request.session.pop("oauth_extra", {})
    redirect_uri = request.session.pop("oauth_redirect_uri", idp_redirect_uri)
    landing_base = request.session.pop("oauth_landing", idp_frontend_landing)
    # state 不一致或 verifier 丢失:典型是用户 F5 刷了 callback 页 / 后退到该 URL /
    # 多 tab 同时登录互相覆盖。这种情况静默重新发起登录流程,体验更顺。
    if not saved or saved != state or not verifier:
        logging.warning(
            "[OAUTH-CALLBACK-REPLAY] state 校验失败,重新发起登录 saved=%s url=%s has_verifier=%s",
            bool(saved), bool(state), bool(verifier),
        )
        return RedirectResponse("/auth/oauth/login", status_code=302)

    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": idp_client_id,
        "client_secret": IdpConf.CLIENT_SECRET,
        "code_verifier": verifier,
    }
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
        async with session.post(
            f"{idp_issuer.rstrip('/')}/oauth/token", data=form
        ) as r:
            if r.status != 200:
                text = await r.text()
                logging.warning("[OAUTH-TOKEN-FAIL] token 交换失败,重新发起登录: %s", text)
                return RedirectResponse("/auth/oauth/login", status_code=302)
            token_json = await r.json()

    jwks = await _get_jwks()
    claims = jwt.decode(
        token_json["id_token"],
        jwks,
        algorithms=["RS256"],
        audience=idp_client_id,
        issuer=idp_issuer,
    )

    username = claims.get("sub")
    if not username:
        return RedirectResponse(f"{landing_base}#error=no_username")

    user = await user_cols.user.find_one({"phone": username})
    if not user:
        user = await _provision_user(claims, request)

    if user.get("status") == 0:
        return RedirectResponse(f"{landing_base}#error=disabled")

    # 建服务端会话,session_id 只走 HttpOnly cookie,不再把 token 丢给前端
    session_id = await create_session(str(user["_id"]), claims.get("sid"))
    landing = landing_base
    if extra:
        landing = f"{landing}#{urlencode(extra)}"
    resp = RedirectResponse(landing)
    set_session_cookie(resp, session_id)
    return resp


# ---- JIT: ERP user_type / dept → 本系统 roles / departments ----

_CREATOR_DEPT = "素材中台"


def _map_roles_and_depts(user_type: str | None, dept_name: str | None) -> tuple[list[str], list[str]]:
    """ERP user_type + dept_name → 本系统 roles + departments。每个用户只给一个角色。"""
    if user_type == "SUPER_ADMIN":
        return ["admin"], ["全部"]
    if user_type == "DEPT_ADMIN":
        return ["operator_leader"], [dept_name] if dept_name else []
    # USER / CREATOR / 其他:按部门归属决定角色
    role = "creator" if dept_name == _CREATOR_DEPT else "operator"
    return [role], [dept_name] if dept_name else []


async def _provision_user(claims: dict, request: Request) -> dict:
    """callback 里发现本地没有该用户时,按 ERP claim 自动开通(JIT)。"""
    from datetime import datetime

    from app.model_type_defs.common_models import SecondFormat

    user_name = claims.get("sub")
    nick_name = claims.get("name") or user_name              # 中文名(ERP nick_name)→ Mongo full_name
    name_abbr = claims.get("name_abbr") or nick_name         # 英文缩写(ERP name_abbr)→ Mongo real_name
    user_type = claims.get("user_type")
    dept_name = claims.get("dept_name")

    roles, departments = _map_roles_and_depts(user_type, dept_name)

    now = datetime.now().strftime(SecondFormat)
    new_doc = {
        "username": user_name,
        "real_name": name_abbr,
        "full_name": nick_name,
        "phone": user_name,
        "roles": roles,
        "department": dept_name,
        "departments": departments,
        "status": 1,
        "create_time": now,
        "provisioned_by": "jit",
    }
    res = await user_cols.user.insert_one(new_doc)
    new_user = await user_cols.user.find_one({"_id": res.inserted_id})

    client_ip = request.client.host if request.client else "unknown"
    logging.warning(
        "[JIT-PROVISION] 新建本地用户 _id=%s username=%s full_name(中文)=%s "
        "real_name(英文)=%s ERP_user_type=%s ERP_dept=%s → roles=%s departments=%s client_ip=%s",
        new_user["_id"], user_name, nick_name, name_abbr,
        user_type, dept_name, roles, departments, client_ip,
    )
    return new_user


@router.get("/logout")
@public
async def oauth_logout(request: Request):
    session_id = request.cookies.get(COOKIE_NAME)
    if session_id:
        await delete_session(session_id)
    request.session.clear()
    # 登出后直接回登录入口,不经过探测落地页(避免一个注定 401 的 /info 调用)
    login_uri = idp_redirect_uri.replace("/callback", "/login")
    params = {"post_logout_redirect_uri": login_uri}
    resp = RedirectResponse(f"{idp_issuer.rstrip('/')}/oauth/logout?{urlencode(params)}")
    clear_session_cookie(resp)
    return resp


@router.post("/backchannel-logout")
@public
async def backchannel_logout(request: Request, logout_token: str = Form(...)):
    """IdP 单点登出回调:验签 logout_token 后把对应 sid 拉黑,持有该 sid 的本地 token 立即失效。"""
    jwks = await _get_jwks()
    try:
        claims = jwt.decode(
            logout_token,
            jwks,
            algorithms=["RS256"],
            audience=idp_client_id,
            issuer=idp_issuer,
        )
    except JWTError:
        return JSONResponse({"error": "invalid logout_token"}, status_code=400)

    if _BACKCHANNEL_LOGOUT_EVENT not in (claims.get("events") or {}):
        return JSONResponse({"error": "not a backchannel logout token"}, status_code=400)
    sid = claims.get("sid")
    if not sid:
        return JSONResponse({"error": "missing sid"}, status_code=400)

    count = await delete_sessions_by_sid(sid)
    logging.warning("[BACKCHANNEL-LOGOUT] sid=%s sub=%s 删除会话数=%s", sid, claims.get("sub"), count)
    return JSONResponse({"status": "ok"})
