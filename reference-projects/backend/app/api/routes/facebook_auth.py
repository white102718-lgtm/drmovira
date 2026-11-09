"""
Facebook 企业登录示例代码
使用 Redis 存储 OAuth state 以验证回调的真实性
"""

import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request, Depends
from fastapi.responses import RedirectResponse
from jose import JWTError, ExpiredSignatureError
from jose import jwt

from app.conf.api_conf import erp_redirect_url, frontend_callback_url, ad_redirect_url
from app.core.security import SECRET_KEY, ALGORITHM
from app.core.security import auth_current_user
from app.core.security import public
from app.db.clients import redis_cli_2 as redis_cli
from app.db.mongo import cols
from app.model_type_defs.common_models import ApiResponse, ErrResponse, SecondFormat
from app.model_type_defs.facebook_models import (
    FacebookTokenResponse,
    FacebookUserInfo,
    FacebookAccountInDB,
)
from app.model_type_defs.user_models import UserModel
from app.services.fb_common import TokenType, push_personal_to_sync_queue

router = APIRouter(prefix="/facebook", tags=["Facebook Auth"])

# OAuth 授权范围 - 根据需要调整
# 企业登录常用权限: ads_management, business_management, pages_manage_posts 等
FACEBOOK_SCOPES = [
    "email",
    "public_profile",
    "ads_management",
    "ads_read",
    "business_management",
    "read_insights",
    "pages_show_list",
    "pages_read_engagement",
    "pages_read_user_content",
]

# Redis Key 配置
REDIS_KEY_PREFIX = "facebook:oauth:state:"
STATE_EXPIRE_SECONDS = 3600  # state 有效期 1 小时


async def generate_and_store_state(
    app_id: str, user_identifier: Optional[str] = Query(None)
) -> str:
    """
    生成 OAuth state 并存储到 Redis

    Args:
        user_identifier: 可选的用户标识，用于在回调时关联用户

    Returns:
        生成的 state 字符串
    """
    # 生成安全的随机 state
    state = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expire = now + timedelta(seconds=STATE_EXPIRE_SECONDS)

    payload = {
        "user_identifier": user_identifier or "",
        "client_id": app_id,
        "state": state,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    # 签名生成JWT
    jwt_token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    # 存储到 Redis，附带用户标识
    redis_key = f"{REDIS_KEY_PREFIX}{jwt_token}"
    await redis_cli.setex(
        redis_key, STATE_EXPIRE_SECONDS, user_identifier or "anonymous"
    )

    return jwt_token


async def verify_and_consume_state(state: str) -> Optional[str]:
    """
    验证 state 是否有效并消费（删除）

    Args:
        state: 回调中返回的 state

    Returns:
        如果有效，返回存储的用户标识；否则返回 None
    """
    if not state:
        return None

    # JWT解码和验证
    try:
        # decode会自动验证签名和exp过期时间
        payload = jwt.decode(state, SECRET_KEY, algorithms=[ALGORITHM])
    except ExpiredSignatureError:
        logging.info("OAuth state已过期")
        return None
    except JWTError as e:
        logging.warning(f"OAuth state JWT验证失败: {str(e)}")
        return None

    redis_key = f"{REDIS_KEY_PREFIX}{state}"

    # 获取并删除（原子操作）
    # 使用 pipeline 确保原子性
    pipe = redis_cli.pipeline()
    pipe.get(redis_key)
    pipe.delete(redis_key)
    results = await pipe.execute()

    user_identifier = payload.get("user_identifier")
    return user_identifier


async def is_state_valid(state: str) -> bool:
    """
    仅检查 state 是否有效（不消费）

    Args:
        state: 要检查的 state

    Returns:
        是否有效
    """
    if not state:
        return False

    redis_key = f"{REDIS_KEY_PREFIX}{state}"
    exists = await redis_cli.exists(redis_key)
    return bool(exists)


async def exchange_short_token_to_long_lived(
    short_token: str, app_id: str, app_secret: str
) -> FacebookTokenResponse:
    """
    将短期 access_token 换取长期 token（有效期约60天）

    Args:
        short_token: 短期 access_token

    Returns:
        FacebookTokenResponse 对象，包含 access_token、token_type、expires_in

    Raises:
        Exception: Token 交换失败时抛出异常
    """
    import aiohttp

    url = "https://graph.facebook.com/v21.0/oauth/access_token"
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": short_token,
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                error_data = await resp.json()
                raise Exception(f"Token 交换失败: {error_data}")
            data = await resp.json()
            return FacebookTokenResponse(
                access_token=data.get("access_token"),
                token_type=data.get("token_type", "bearer"),
                expires_in=data.get(
                    "expires_in", 7776000
                ),  # 长期 token 约 5184000 秒（60天）
            )


async def save_facebook_account_to_mongo(account: FacebookAccountInDB) -> str:
    """
    保存/更新 Facebook 账户信息到 MongoDB
    使用 upsert 操作确保唯一性

    Args:
        account: FacebookAccountInDB 对象，包含账户的所有信息

    Returns:
        MongoDB document 的 _id（字符串形式）

    Raises:
        Exception: 数据库操作失败时抛出异常
    """
    try:
        collection = cols.personal_accounts

        result = await collection.update_one(
            {
                "_id": account.facebook_id,
                "app_id": account.app_id,
            },
            {
                "$set": {
                    "name": account.name,
                    "email": account.email,
                    "access_token": account.access_token,
                    "app_secret": account.app_secret,
                    "expires_in": account.expires_in,
                    "updated_at": account.updated_at,
                    "status": account.status,
                    "user_name": account.user_name,
                },
                "$setOnInsert": {"created_at": account.created_at},
            },
            upsert=True,
        )
        return str(result.upserted_id or account.facebook_id)
    except Exception as e:
        raise Exception(f"保存 Facebook 账户到 MongoDB 失败: {str(e)}")


async def save_token_to_redis(
    facebook_id: str, app_id: str, access_token: str, expires_in: int
):
    """
    保存 token 到 Redis，用于过期校验
    Key 格式: fb:token:{facebook_id}:{app_id}
    Value 格式: JSON 字符串 {"access_token": "xxx", "expires_in": 5184000}
    使用 setex 设置过期时间

    Args:
        facebook_id: Facebook 用户 ID
        app_id: Facebook 应用 ID
        access_token: 长期 access_token
        expires_in: token 有效期（秒）

    Raises:
        Exception: Redis 操作失败时抛出异常
    """
    try:
        redis_key = f"fb:token:{facebook_id}:{app_id}"
        token_data = {
            "access_token": access_token,
            "expires_in": expires_in,
        }
        await redis_cli.setex(redis_key, expires_in, json.dumps(token_data))
    except Exception as e:
        raise Exception(f"保存 token 到 Redis 失败: {str(e)}")


async def facebook_auther(
    app_id: str,
    facebook_redirect_uri: str,
    config_id: str,
    user_name: Optional[str] = Query(None),
) -> str:
    """
    发起 Facebook OAuth 登录

    重定向用户到 Facebook 授权页面
    """
    # 生成并存储 state
    state = await generate_and_store_state(app_id=app_id, user_identifier=user_name)

    # 构建 Facebook OAuth 授权 URL
    params = {
        "client_id": app_id,
        "redirect_uri": facebook_redirect_uri,
        "scope": ",".join(FACEBOOK_SCOPES),
        "response_type": "code",
        "config_id": config_id,
        "state": state,
    }

    auth_url = f"https://www.facebook.com/v21.0/dialog/oauth?{urlencode(params)}"

    return auth_url


async def facebook_callback_auther(
    app_id: str,
    app_secret: str,
    proxy: str,
    redirect_uri: str,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
) -> tuple[bool, str]:
    """
    Facebook OAuth 回调处理

    验证 state, 用 code 换取 access_token
    自动换取长期 token（60天有效期）
    存储用户信息到 MongoDB
    存储 token 和任务信息到 Redis
    返回 JSON 响应
    """
    # 处理错误响应
    if error:
        error_msg = f"{error}"
        if error_description:
            error_msg += f" - {error_description}"
        return False, error_msg

    # 验证必要参数
    if not code or not state:
        error_msg = "缺少必要参数: code 或 state"
        return False, error_msg

    # 验证 state 有效性（防止 CSRF 攻击）
    user_identifier = await verify_and_consume_state(state)
    if user_identifier is None:
        error_msg = "无效或过期的 state，请重新发起登录"
        return False, error_msg

    # 使用 code 换取 access_token
    import aiohttp

    token_url = "https://graph.facebook.com/v21.0/oauth/access_token"
    token_params = {
        "client_id": app_id,
        "client_secret": app_secret,
        "redirect_uri": redirect_uri,
        "code": code,
    }

    try:
        async with aiohttp.ClientSession() as session:
            # 获取短期 access_token
            async with session.get(token_url, params=token_params) as resp:
                if resp.status != 200:
                    error_data = await resp.json()
                    error_msg = f"获取 access_token 失败: {error_data}"
                    return False, error_msg
                short_token_data = await resp.json()

            short_access_token = short_token_data.get("access_token")
            if not short_access_token:
                error_msg = "未获取到 access_token"
                return False, error_msg

            # 获取用户信息
            user_url = "https://graph.facebook.com/v21.0/me"
            user_params = {
                "access_token": short_access_token,
                "fields": "id,name,email",
            }

            async with session.get(user_url, params=user_params) as resp:
                if resp.status != 200:
                    error_data = await resp.json()
                    error_msg = f"获取用户信息失败: {error_data}"
                    return False, error_msg
                user_data = await resp.json()

        # 【改进】使用 FacebookUserInfo 验证用户数据
        user_info = FacebookUserInfo(**user_data)

        # 【改进】将短期 token 换取长期 token，使用 Pydantic 对象
        try:
            token_response = await exchange_short_token_to_long_lived(
                short_access_token, app_id=app_id, app_secret=app_secret
            )
            access_token = token_response.access_token
            expires_in = token_response.expires_in  # 默认 60 天
        except Exception as e:
            error_msg = f"换取长期 token 失败: {str(e)}"
            return False, error_msg

        # 【改进】准备 FacebookAccountInDB 对象
        now = datetime.now().strftime(SecondFormat)
        account = FacebookAccountInDB(
            facebook_id=user_info.id,
            name=user_info.name,
            email=user_info.email,
            app_id=app_id,
            app_secret=app_secret,
            access_token=access_token,
            expires_in=expires_in,
            created_at=now,
            updated_at=now,
            status=True,
            user_name=user_identifier,
        )

        await save_facebook_account_to_mongo(account)

        await save_token_to_redis(
            facebook_id=user_info.id,
            app_id=app_id,
            access_token=access_token,
            expires_in=expires_in,
        )

        await push_personal_to_sync_queue(
            facebook_id=user_info.id,
            personal_type=TokenType.PERSONAL,
            app_id=app_id,
            app_secret=app_secret,
            access_token=access_token,
            proxy=proxy,
        )
        return True, "success"
    except Exception as e:
        error_msg = f"回调处理出错: {str(e)}"
        return False, error_msg


@router.get("/login")
@public
async def facebook_login(
    request: Request,
    user_id: Optional[str] = Query(None, description="可选的用户ID，用于回调时关联"),
):
    """
    发起 Facebook OAuth 登录

    重定向用户到 Facebook 授权页面
    """
    app_id = "1156297120038785"
    facebook_redirect_uri = erp_redirect_url
    config_id = "1185202226370964"

    auth_url = await facebook_auther(
        app_id=app_id,
        user_name=user_id,
        config_id=config_id,
        facebook_redirect_uri=facebook_redirect_uri,
    )

    return ApiResponse(data=f"{auth_url}_notErp")


@router.get("/callback")
@public
async def facebook_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
):
    app_id = "1156297120038785"
    app_secret = "REDACTED_REFERENCE_SECRET"
    facebook_redirect_uri = frontend_callback_url
    try:
        result = await facebook_callback_auther(
            app_id=app_id,
            app_secret=app_secret,
            redirect_uri=erp_redirect_url,
            code=code,
            state=state,
            error=error,
            error_description=error_description,
        )
        if result[0]:
            # 如果是True
            # 成功重定向到前端 callback 页面，带上 success 状态

            redirect_url = f"{facebook_redirect_uri}?status=success"
            return ApiResponse(data=redirect_url)
        else:
            error_msg = f"回调处理错误: {str(result[1])}"
            return ErrResponse(data=error_msg)

    except Exception as e:
        error_msg = f"回调处理出错: {str(e)}"
        return ErrResponse(data=error_msg)


@router.get("/effective/appid")
async def get_effective_appid(
    request: Request,
):
    cursor = cols.accounts.find(
        {
            "account_usage.facebook_login": True,
            "status": 1,
            "app_id": {"$ne": "1156297120038785"},
        },
        projection={"app_id": 1, "config_id": 1, "_id": 0},
    )

    docs = await cursor.to_list(length=None)

    data = {
        f"adpluse_{item['app_id'][-4:]}": {
            "app_id": item["app_id"],
            "config_id": item["config_id"],
        }
        for item in docs
        if item.get("app_id")
    }

    return ApiResponse(data=data)


@router.get("/advertising/login")
async def advertising_login(
    request: Request,
    app_id: str,
    config_id: str,
    current_user: UserModel = Depends(auth_current_user),
):
    """
    发起 Facebook OAuth 登录

    重定向用户到 Facebook 授权页面
    广告系统额外用的
    """
    facebook_redirect_uri = (
        f"https://{request.url.hostname}/backend/facebook/advertising/callback"
    )

    auth_url = await facebook_auther(
        app_id=app_id,
        user_name=current_user.real_name,
        config_id=config_id,
        facebook_redirect_uri=facebook_redirect_uri,
    )

    return ApiResponse(data=auth_url)


@router.get("/advertising/callback")
@public
async def advertising_callback(
    request: Request,
    code: str,
    state: str,
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
):
    jwt_param = jwt.decode(
        state,
        SECRET_KEY,
        algorithms=[ALGORITHM],
    )

    app_id = jwt_param["client_id"]
    # 查询accounts表
    dev_config = await cols.accounts.find_one(
        {"app_id": app_id, "account_usage.facebook_login": True, "status": 1},
        projection={"app_secret": 1, "proxy": 1},
    )
    app_secret = dev_config.get("app_secret")
    facebook_redirect_uri = f"https://{request.url.hostname}/management/platform-config"

    try:
        result = await facebook_callback_auther(
            app_id=app_id,
            app_secret=app_secret,
            proxy=dev_config.get("proxy"),
            redirect_uri=ad_redirect_url,
            code=code,
            state=state,
            error=error,
            error_description=error_description,
        )
        if result[0]:
            # 如果是True
            # 成功重定向到前端 callback 页面，带上 success 状态
            redirect_url = f"{facebook_redirect_uri}?status=success"
            return RedirectResponse(url=redirect_url)
        else:
            redirect_url = f"{facebook_redirect_uri}?status={result[1]}"
            return RedirectResponse(url=redirect_url)
    except Exception as e:
        redirect_url = f"{facebook_redirect_uri}?status={e}"
        return RedirectResponse(url=redirect_url)


@router.post("/exchange-long-lived-token")
async def exchange_long_lived_token(short_lived_token: str):
    """
    将短期 access_token 换取长期 token（有效期约60天）

    企业应用通常需要长期 token 来管理广告等
    """
    import aiohttp

    app_id = ""
    app_secret = ""

    url = "https://graph.facebook.com/v21.0/oauth/access_token"
    params = {
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": short_lived_token,
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                error_data = await resp.json()
                return ErrResponse(
                    code=resp.status, message=f"Token 交换失败: {error_data}"
                )
            data = await resp.json()

    return ApiResponse(
        data={
            "access_token": data.get("access_token"),
            "token_type": data.get("token_type", "bearer"),
            "expires_in": data.get("expires_in"),  # 长期 token 约 5184000 秒（60天）
        }
    )


@router.get("/ad-accounts")
async def get_ad_accounts(
    access_token: str = Query(..., description="用户的 access_token")
):
    """
    获取用户有权限的广告账户列表

    需要 ads_management 或 ads_read 权限
    """
    import aiohttp

    url = "https://graph.facebook.com/v21.0/me/adaccounts"
    params = {
        "access_token": access_token,
        "fields": "id,name,account_id,account_status,currency,timezone_name",
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                error_data = await resp.json()
                return ErrResponse(
                    code=resp.status, message=f"获取广告账户失败: {error_data}"
                )
            data = await resp.json()

    return ApiResponse(data=data.get("data", []))


@router.get("/businesses")
async def get_businesses(
    access_token: str = Query(..., description="用户的 access_token")
):
    """
    获取用户关联的 Business Manager 列表

    需要 business_management 权限
    """
    import aiohttp

    url = "https://graph.facebook.com/v21.0/me/businesses"
    params = {
        "access_token": access_token,
        "fields": "id,name,created_time,primary_page",
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                error_data = await resp.json()
                return ErrResponse(
                    code=resp.status,
                    message=f"获取 Business Manager 失败: {error_data}",
                )
            data = await resp.json()

    return ApiResponse(data=data.get("data", []))
