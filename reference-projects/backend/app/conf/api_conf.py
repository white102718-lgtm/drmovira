"""非 secret 的对外 URL,按部署环境写死,不走加密 env_vault。"""

from env_vault.env_conf import Env, env
import os

# ERP 登录回调,三套环境一致
erp_redirect_url = "https://api.tango-game.com/admin-server/auth"

_ADS_API = {
    Env.DEV: "http://localhost:8062",
    Env.TEST: "http://localhost:8062",
    Env.PROD: "http://0.0.0.00:8079",
}

_AD_REDIRECT_URL = {
    Env.DEV: "https://pengyuyan.xyz/facebook/advertising/callback",
    Env.TEST: "https://pengyuyan.xyz/facebook/advertising/callback",
    Env.PROD: "https://adpulse.biz/backend/facebook/advertising/callback",
}

_FRONTEND_CALLBACK_URL = {
    Env.DEV: "http://172.31.44.138:5555/management/platform-config",
    Env.TEST: "http://54.179.56.204:5555/management/platform-config",
    Env.PROD: "https://adpulse.biz/management/platform-config",
}

# IdP(auth-server)非 secret 信息;secret(client_secret / session_secret)仍走 env_vault
_IDP_ISSUER = {
    # Env.DEV: "http://localhost:9100",
    Env.DEV: "http://54.179.56.204:9100",
    Env.TEST: "http://54.179.56.204:9100",
    Env.PROD: "https://idp.adpulse.biz",
}

_IDP_CLIENT_ID = {
    Env.DEV: "backend-a",
    Env.TEST: "backend-a",
    Env.PROD: "adpulse",
}

_IDP_REDIRECT_URI = {
    Env.DEV: "http://localhost:8000/auth/oauth/callback",
    Env.TEST: "http://54.179.56.204:5555/backend/auth/oauth/callback",
    Env.PROD: "https://adpulse.biz/backend/auth/oauth/callback",
}

_IDP_FRONTEND_LANDING = {
    Env.DEV: "http://localhost:5555/oauth-landing",
    Env.TEST: "http://54.179.56.204:5555/oauth-landing",
    Env.PROD: "https://adpulse.biz/oauth-landing",
}

# dev 兜底复用 test
ads_api = _ADS_API.get(env, _ADS_API[Env.TEST])
ad_redirect_url = _AD_REDIRECT_URL.get(env, _AD_REDIRECT_URL[Env.TEST])
frontend_callback_url = _FRONTEND_CALLBACK_URL.get(env, _FRONTEND_CALLBACK_URL[Env.TEST])
idp_issuer = _IDP_ISSUER.get(env, _IDP_ISSUER[Env.TEST])
idp_client_id = _IDP_CLIENT_ID.get(env, _IDP_CLIENT_ID[Env.TEST])
idp_redirect_uri = _IDP_REDIRECT_URI.get(env, _IDP_REDIRECT_URI[Env.TEST])
idp_frontend_landing = _IDP_FRONTEND_LANDING.get(env, _IDP_FRONTEND_LANDING[Env.TEST])


# 代理配置
PROXY_CONFIG = {
    "username": os.environ["PROXY_USER"],
    "password": os.environ["PROXY_PASS"],
    "port": int(os.environ["PROXY_PORT"]),
}


def format_proxy_url(proxy_host: str, protocol: str = "socks5") -> str:
    """
    格式化代理 URL

    Args:
        proxy_host: 代理主机地址（IP 或域名）
        protocol: 代理协议，默认 "socks5"，也可以是 "socks5h", "http" 等

    Returns:
        完整的代理 URL，格式: protocol://username:REDACTED_REFERENCE_SECRET@host:port
    """
    return (
        f"{protocol}://{PROXY_CONFIG['username']}:{PROXY_CONFIG['password']}"
        f"@{proxy_host}:{PROXY_CONFIG['port']}"
    )


def get_proxies(proxy_host: str, protocol: str = "socks5h"):
    if not proxy_host:
        raise ValueError("get_proxies: proxy_host 必传且非空")
    proxy_url = format_proxy_url(proxy_host, protocol)
    return {"http": proxy_url, "https": proxy_url}
