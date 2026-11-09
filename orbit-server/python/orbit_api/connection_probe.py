"""只读认证适配器：固定官方源、GET、禁止重定向和代理环境，不生成AI内容。"""

import asyncio
import json
import re
from dataclasses import dataclass
from urllib.parse import quote

import httpx


@dataclass(frozen=True)
class ProbeResult:
    status: str
    message: str


BLOCKED = ProbeResult("BLOCKED", "当前配置条件或连接器尚不支持只读认证验证")
FAILED = ProbeResult("FAILED", "只读认证未通过，请核对配置或稍后重试")
VERIFIED = ProbeResult("READ_VERIFIED", "只读模型查询已通过；不代表内容生成或广告写入能力")
GRAPH_VERIFIED = ProbeResult("READ_VERIFIED", "只读应用或BM对象查询已通过；不代表广告写入能力")


class ModelConnectionProbe:
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None):
        # 测试仅替换HTTP传输，不允许浏览器或运行环境提供任意目标URL。
        self.transport = transport

    async def run(self, section: str, enabled: bool, settings: dict, api_key: str | None):
        if not enabled or section not in {"AI_GPT", "AI_CLAUDE", "META_APP", "META_BM"}:
            return BLOCKED
        graph = section in {"META_APP", "META_BM"}
        model = settings.get(
            "appId" if section == "META_APP" else "businessId" if graph else "model", ""
        )
        if (
            not isinstance(model, str)
            or not model
            or model in {".", ".."}
            or not isinstance(api_key, str)
            or not api_key
        ):
            return BLOCKED
        params = None
        if graph:
            version = settings.get("graphVersion", "")
            if not re.fullmatch(r"[0-9]{1,64}", model) or not re.fullmatch(
                r"v[0-9]{1,3}\.[0-9]{1,2}", version
            ):
                return BLOCKED
            target = "https://graph.facebook.com/" + version + "/" + model
            params = {"fields": "id,name"}
            if section == "META_APP":
                api_key = model + "|" + api_key
        elif section == "AI_GPT":
            target = "https://api.openai.com/v1/models/" + quote(model, safe="")
        else:
            target = "https://api.anthropic.com/v1/models/" + quote(model, safe="")
        headers = {"Authorization": "Bearer " + api_key, "Accept": "application/json"}
        if section == "AI_CLAUDE":
            version = settings.get("apiVersion", "")
            workspace = settings.get("workspaceId", "")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", version):
                return BLOCKED
            headers["anthropic-version"] = version
            if workspace:
                if not isinstance(workspace, str) or not re.fullmatch(
                    r"wrkspc_[A-Za-z0-9]+", workspace
                ):
                    return BLOCKED
                headers["anthropic-workspace-id"] = workspace
        timeout = settings.get("timeoutSeconds", 60)
        if type(timeout) is not int or not 1 <= timeout <= 60:
            return BLOCKED
        try:
            # 整个探测有绝对时限；失败不自动重发，前端可明确再次发起。
            async with (
                asyncio.timeout(timeout),
                httpx.AsyncClient(
                    transport=self.transport,
                    follow_redirects=False,
                    trust_env=False,
                    timeout=timeout,
                ) as client,
            ):
                async with client.stream("GET", target, headers=headers, params=params) as response:
                    if response.status_code != 200:
                        return FAILED
                    if (
                        response.headers.get("content-type", "").split(";", 1)[0]
                        != "application/json"
                    ):
                        return FAILED
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(data) + len(chunk) > 65_536:
                            return FAILED
                        data.extend(chunk)
                    result = json.loads(data)
                    # Claude支持模型别名解析，不能强求返回ID等于输入别名。
                    if not isinstance(result, dict) or not isinstance(result.get("id"), str):
                        return FAILED
                    if not result["id"] or len(result["id"]) > 500:
                        return FAILED
                    if graph:
                        if "error" in result or result["id"] != model:
                            return FAILED
                        return GRAPH_VERIFIED
                    if section == "AI_GPT" and result.get("object") != "model":
                        return FAILED
                    if section == "AI_CLAUDE" and result.get("type") != "model":
                        return FAILED
                    return VERIFIED
        except (httpx.HTTPError, TimeoutError, ValueError, UnicodeError):
            # 平台响应、异常消息和请求头都不进入API结果、审计或日志。
            return FAILED
