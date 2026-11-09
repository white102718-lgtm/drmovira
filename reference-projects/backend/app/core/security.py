import logging
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Callable, Set

from bson import ObjectId
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, APIKeyHeader
from jose import jwt

from app.core.session_store import COOKIE_NAME, get_session
from app.db.mongo import user_cols
from app.model_type_defs.user_models import UserModel, Roles

# facebook_auth 用这两个常量签 / 验 OAuth state JWT;同源兄弟服务(automationApi/aiReport)也用同一把 key 验转发 token
ALGORITHM = "HS256"
SECRET_KEY = "REDACTED_REFERENCE_SECRET"

# 本地会话走 cookie,但同源兄弟服务仍按 Bearer JWT 识别用户,这里签一个转发用 token
FORWARD_TOKEN_TTL_SECONDS = 7 * 24 * 3600


def make_forward_token(user_id, roles: List[str]) -> str:
    payload = {
        "sub": str(user_id),
        "roles": roles,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=FORWARD_TOKEN_TTL_SECONDS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/oauth/login", auto_error=False)
api_key_header = APIKeyHeader(name="X-Api-Key", auto_error=False)


def public(fn: Callable):
    """标记：完全公开，跳过所有鉴权"""
    setattr(fn, "__public__", True)
    return fn


def skip_ip_auth(*ip_patterns: str):
    """
    标记：匹配IP模式可跳过鉴权, 支持精确匹配和正则表达式匹配。
    用法：
      @skip_ip_auth("1.2.3.4", "172.*") - 匹配精确IP 1.2.3.4 或所有172开头的IP
      @skip_ip_auth("10.*", "192.168.*") - 匹配所有10.和192.168.开头的IP
    注意：正则表达式中，点号(.)默认匹配任意字符，如果要精确匹配点号字符，请使用转义\\.
    """
    compiled_patterns = []
    exact_ips = set()

    for pattern in ip_patterns:
        # 使用更精确的方式检查是否为正则表达式
        # 简单的IP地址格式检查：是否符合IPv4地址的格式 (如 127.0.0.1)
        if re.match(r"^(\d{1,3}\.){3}\d{1,3}$", pattern):
            # 这是标准IPv4地址格式，视为精确匹配
            exact_ips.add(pattern)
        else:
            # 包含特殊正则字符或不是标准IPv4格式，视为正则表达式
            try:
                compiled_patterns.append(re.compile(pattern))
            except re.error:
                # 如果正则表达式无效，作为普通字符串处理
                exact_ips.add(pattern)

    def decorator(fn: Callable):
        setattr(fn, "__skip_ip_auth_exact__", exact_ips)
        setattr(fn, "__skip_ip_auth_patterns__", compiled_patterns)
        return fn

    return decorator


def raise_and_log(endpoint, client_ip, message):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
        headers={"WWW-Authenticate": "Bearer"},
    )
    logging.warning(f"安全校验不通过,{message}{client_ip},{endpoint}")
    return credentials_exception


async def auth_current_user(
    api_key: str = Depends(api_key_header),
    request: Request = None,
) -> Optional[UserModel] | bool:
    endpoint = request.scope.get("endpoint")
    client_ip = request.client.host

    # API Key 认证
    if api_key:
        collection = user_cols.user
        user = await collection.find_one({"api_keys.key": api_key})
        if not user or user.get("status", 1) == 0:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key 无效或已禁用")
        entry = next((k for k in user.get("api_keys", []) if k["key"] == api_key), None)
        if not entry:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key 无效")
        if entry.get("expires_at") and datetime.now() > datetime.strptime(entry["expires_at"], "%Y-%m-%d %H:%M:%S"):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key 已过期")
        return UserModel(**user)

    # 会话存 Redis,删 key 即登出;roles 每次从库读,改权限立即生效
    session_id = request.cookies.get(COOKIE_NAME)
    session = await get_session(session_id) if session_id else None

    if session is None:
        # 无有效会话(没 cookie,或 sess 已删 / 过期):公开端点 / IP 白名单放行,否则拒
        if getattr(endpoint, "__public__", False):
            return True
        if hasattr(endpoint, "__skip_ip_auth_exact__"):
            exact_ips: Set[str] = getattr(endpoint, "__skip_ip_auth_exact__")
            if client_ip in exact_ips:
                return True
        if hasattr(endpoint, "__skip_ip_auth_patterns__"):
            ip_patterns = getattr(endpoint, "__skip_ip_auth_patterns__")
            if any(pattern.match(client_ip) for pattern in ip_patterns):
                return True
        raise raise_and_log(endpoint, client_ip, "无登录凭据或会话已失效")

    user = await user_cols.user.find_one({"_id": ObjectId(session["user_id"])})
    if user is None:
        raise raise_and_log(endpoint, client_ip, "未查询到用户")
    if user.get("status", 1) == 0:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账号已禁用")

    ip_list = user.get("ips", [])
    if ip_list and client_ip not in ip_list:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="当前IP地址未授权访问"
        )

    return UserModel(**user)


def require_roles(required_roles: List[str]):
    def role_checker(user: UserModel = Depends(auth_current_user)) -> UserModel:
        if user is True:
            # auth_current_user() 可能返回True表示不需要鉴权
            return user
        if Roles.ADMIN not in user.roles and not any(
            role in user.roles for role in required_roles
        ):
            logging.error(f"权限检查失败: user.roles={user.roles}, required={required_roles}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="没有权限操作"
            )
        return user

    return role_checker
