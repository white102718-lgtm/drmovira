"""AdsPower只读/status探测；仅证明本机API可用，不推导登录、Profile或写能力。

官方合同：https://localapi-doc-en.adspower.com/docs/6DSiws
API Key头合同：https://localapi-doc-en.adspower.com/docs/Rdw7Iu
"""

import argparse
import asyncio
import json
import math
import os
import re
import stat
from pathlib import Path

import httpx

MAX_RESPONSE_BYTES = 4096
MAX_KEY_BYTES = 4096
DEFAULT_ENDPOINT = "http://127.0.0.1:50325"


class ProbeError(Exception):
    """固定安全错误码；不携带HTTP原文、异常URL、本地文件路径或密钥。"""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def canonical_endpoint(endpoint, *, allowed_ports=frozenset({50325})):
    """严格白名单，localhost固定映射127.0.0.1，不进行DNS解析或接受等价IP拼写。"""
    match = re.fullmatch(r"http://(?:127\.0\.0\.1|localhost):([1-9][0-9]{0,4})/?", endpoint)
    if match is None:
        raise ProbeError("ENDPOINT_REJECTED")
    port = int(match[1])
    if port > 65535 or port not in allowed_ports:
        raise ProbeError("ENDPOINT_REJECTED")
    return f"http://127.0.0.1:{port}"


def read_api_key(path):
    """仅显式本机文件引用；拒绝符号链接、非本人私有文件、超长内容及头注入。"""
    descriptor = None
    try:
        path = Path(path)
        if not path.is_absolute():
            raise ProbeError("API_KEY_FILE_REJECTED")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) & 0o077
            or info.st_size > MAX_KEY_BYTES
        ):
            raise ProbeError("API_KEY_FILE_REJECTED")
        raw = os.read(descriptor, MAX_KEY_BYTES + 1)
        if len(raw) > MAX_KEY_BYTES:
            raise ProbeError("API_KEY_FILE_REJECTED")
        key = raw.decode("ascii").removesuffix("\n").removesuffix("\r")
        if not key or any(not 33 <= ord(char) <= 126 for char in key):
            raise ProbeError("API_KEY_FILE_REJECTED")
        return key
    except (OSError, UnicodeError, TypeError, ValueError):
        raise ProbeError("API_KEY_FILE_REJECTED") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _unique_object(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result


async def probe_status(
    endpoint=DEFAULT_ENDPOINT,
    *,
    allowed_ports=frozenset({50325}),
    api_key_file=None,
    timeout_seconds=3.0,
):
    """单次有界GET；无重试、代理、重定向、Cookie、Profile查询或进程启动。"""
    target = canonical_endpoint(endpoint, allowed_ports=allowed_ports)
    if (
        type(timeout_seconds) not in (int, float)
        or not math.isfinite(timeout_seconds)
        or not 0 < timeout_seconds <= 10
    ):
        raise ProbeError("TIMEOUT_REJECTED")
    headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
    if api_key_file is not None:
        headers["Authorization"] = "Bearer " + read_api_key(api_key_file)
    try:
        # 总截止时间包含连接、响应头和所有流片段，不能被慢速滴流延长。
        async with asyncio.timeout(timeout_seconds):
            async with httpx.AsyncClient(
                trust_env=False,
                follow_redirects=False,
                timeout=httpx.Timeout(timeout_seconds),
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
            ) as client:
                async with client.stream("GET", target + "/status", headers=headers) as response:
                    if 300 <= response.status_code < 400:
                        raise ProbeError("REDIRECT_REJECTED")
                    if response.status_code in (401, 403):
                        raise ProbeError("AUTHENTICATION_REQUIRED")
                    if response.status_code != 200:
                        raise ProbeError("HTTP_STATUS_REJECTED")
                    if sum(len(k) + len(v) for k, v in response.headers.raw) > 8192:
                        raise ProbeError("RESPONSE_TOO_LARGE")
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise ProbeError("RESPONSE_ENCODING_REJECTED")
                    declared = response.headers.get("content-length")
                    if declared is not None:
                        if not declared.isascii() or not declared.isdecimal():
                            raise ProbeError("RESPONSE_INVALID")
                        if len(declared) > 8 or int(declared) > MAX_RESPONSE_BYTES:
                            raise ProbeError("RESPONSE_TOO_LARGE")
                    body = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=MAX_RESPONSE_BYTES):
                        if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise ProbeError("RESPONSE_TOO_LARGE")
                        body.extend(chunk)
        value = json.loads(body, object_pairs_hook=_unique_object)
        if not isinstance(value, dict) or type(value.get("code")) is not int:
            raise ProbeError("RESPONSE_INVALID")
        if value["code"] != 0:
            raise ProbeError("API_UNAVAILABLE")
        return {
            "api_status": "AVAILABLE",
            "profile_status": "UNKNOWN",
            "meta_login_status": "UNKNOWN",
            "execution_capability": "UNVERIFIED",
        }
    except (TimeoutError, httpx.TimeoutException):
        raise ProbeError("PROBE_TIMEOUT") from None
    except httpx.HTTPError:
        raise ProbeError("CONNECTION_FAILED") from None
    except (ValueError, UnicodeError, RecursionError):
        raise ProbeError("RESPONSE_INVALID") from None
    finally:
        # 不保留可变headers中的秘密；不声称可清零Python/httpx内存副本。
        headers.pop("Authorization", None)


def main(argv=None):
    """本机手工诊断入口；永远只调用/status，不发现密钥、不启动浏览器。"""
    parser = argparse.ArgumentParser(description="执行机本地AdsPower只读/status检查")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--allow-port", type=int, action="append", default=[])
    parser.add_argument("--api-key-file", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=3.0)
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(
            probe_status(
                args.endpoint,
                allowed_ports={50325, *args.allow_port},
                api_key_file=args.api_key_file,
                timeout_seconds=args.timeout_seconds,
            )
        )
    except ProbeError as error:
        print(
            json.dumps({"api_status": "UNAVAILABLE", "error_code": error.code}, ensure_ascii=False)
        )
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
