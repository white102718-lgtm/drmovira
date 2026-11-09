import os

from env_vault.env_conf import Env, env

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


# 内部服务地址,非 secret,按环境写死
_DATA_API = {
    Env.DEV: "http://localhost:7001",
    Env.TEST: "http://localhost:7001",
    Env.PROD: "http://172.31.37.225:7001",
}

_BACKEND_API = {
    Env.DEV: "http://localhost:8000",
    Env.TEST: "http://localhost:8000",
    Env.PROD: "http://172.31.37.225:8000",
}

data_api = _DATA_API.get(env, _DATA_API[Env.TEST])
backend_api = _BACKEND_API.get(env, _BACKEND_API[Env.TEST])
