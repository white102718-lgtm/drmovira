"""API基址纯解析；登记不联网，实际连接仅由持有设备证书的执行机发起。"""

import ipaddress
import re
from urllib.parse import urlsplit


def normalize_endpoint(value):
    """接受HTTP(S)、域名/IP、自定义端口及代理路径；凭据必须独立保存。"""
    if not isinstance(value, str) or not 1 <= len(value) <= 255:
        raise ValueError("ENDPOINT_REJECTED")
    if re.search(r"[^\x21-\x7e]|[\\?#@]", value):
        raise ValueError("ENDPOINT_REJECTED")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
        raise ValueError("ENDPOINT_REJECTED")
    host = parsed.hostname.lower()
    port = parsed.port
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("ENDPOINT_REJECTED")
    raw_port = parsed.netloc.rsplit(":", 1)[-1] if not parsed.netloc.endswith("]") else None
    if ":" in parsed.netloc and raw_port is not None:
        if not re.fullmatch(r"[1-9][0-9]{0,4}", raw_port):
            raise ValueError("ENDPOINT_REJECTED")
    if ":" in host:
        host = "[" + str(ipaddress.IPv6Address(host)) + "]"
    elif re.fullmatch(r"[0-9.]+", host):
        host = str(ipaddress.IPv4Address(host))
    elif not all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part) for part in host.split(".")
    ):
        raise ValueError("ENDPOINT_REJECTED")
    if host == "localhost":
        host = "127.0.0.1"
    path = parsed.path.rstrip("/")
    if not re.fullmatch(r"(?:/[A-Za-z0-9_~.-]+)*", path) or any(
        part in {".", ".."} for part in path.split("/")
    ):
        raise ValueError("ENDPOINT_REJECTED")
    suffix = (
        f":{port}" if port is not None and port != (443 if parsed.scheme == "https" else 80) else ""
    )
    return f"{parsed.scheme}://{host}{suffix}{path}"
