"""现有Meta页面只读DOM观察；V2仅接受已验证结构的跨页账户与账单证据。

Facebook首页登录菜单不是广告账户/币种证明；不导航、不点击、
不开关Profile、不读取Cookie/Storage/网络请求或完整DOM文本，也不上传调试地址。
"""

import asyncio
import hashlib
import json
from urllib.parse import urlsplit

from orbit_agent.adspower_readonly import cdp_endpoint
from orbit_agent.adspower_status import ProbeError, _unique_object
from orbit_agent.meta_dom_v2 import DOM_EXPRESSION_V2, classify_pages

DOM_EXPRESSION = r"""(() => {
 const visible = e => !!e && e.getClientRects().length > 0 &&
   getComputedStyle(e).visibility !== 'hidden' && getComputedStyle(e).display !== 'none';
 const any = selector => Array.from(document.querySelectorAll(selector)).some(visible);
 const reauth = ['www.facebook.com', 'business.facebook.com', 'adsmanager.facebook.com']
   .includes(location.hostname) && /^\/security\/twofactor\/reauth\/?$/.test(location.pathname);
 return {
   password: any('input[type="password"]'),
   challenge: reauth || any('input[name="approvals_code"],input[name="captcha_response"],' +
     'iframe[src*="captcha"]'),
   account_menu: any('[aria-label="Your profile"],[aria-label="Account"],' +
     '[aria-label="你的个人主页"],[aria-label="帐户"]'),
   ads_manager: /Ads Manager|广告管理工具|廣告管理員/.test(document.title),
   currency_marker: false
 };
})()"""
ALLOWED_HOSTS = {"www.facebook.com", "business.facebook.com", "adsmanager.facebook.com"}


def select_existing_target(targets):
    if type(targets) is not list or len(targets) > 100:
        raise ProbeError("CDP_UNAVAILABLE")
    selected, challenges = [], []
    for target in targets:
        if type(target) is not dict or target.get("type") != "page":
            continue
        parsed = urlsplit(target.get("url", ""))
        if parsed.scheme == "https" and parsed.hostname in ALLOWED_HOSTS:
            selected.append(target)
            if parsed.path in {"/security/twofactor/reauth", "/security/twofactor/reauth/"}:
                challenges.append(target)
    # 只优先检查已知挑战页，不读取其他验证码页面；V1不推导多页有效身份。
    if challenges:
        return challenges[0]
    if len(selected) != 1:
        raise ProbeError("IDENTITY_PROBE_FAILED")
    return selected[0]


def classify_dom(facts, expected_account_id, expected_currency):
    keys = {"password", "challenge", "account_menu", "ads_manager", "currency_marker"}
    if (
        type(facts) is not dict
        or set(facts) != keys
        or any(type(v) is not bool for v in facts.values())
    ):
        raise ProbeError("IDENTITY_PROBE_FAILED")
    state, reason = "UNKNOWN", "ACCOUNT_CURRENCY_NOT_OBSERVED"
    if facts["challenge"]:
        state, reason = "CHALLENGE", "VISIBLE_CHALLENGE"
    elif facts["password"]:
        state, reason = "LOGIN_REQUIRED", "VISIBLE_PASSWORD_INPUT"
    elif facts["ads_manager"]:
        reason = "ADS_MANAGER_LAYOUT_UNVERIFIED"
    # expected IDs never become observed facts; no URL/title/currency marker can establish VALID.
    evidence = {"adapter": "ADSPOWER_META_DOM_V1", "facts": facts, "state": state, "reason": reason}
    return {
        "identity_state": state,
        "external_account_id": None,
        "currency": None,
        "reason": reason,
        "evidence_sha256": hashlib.sha256(
            json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


async def inspect_existing_page(endpoint, expected_account_id, expected_currency):
    facts = await observe_existing_pages(endpoint)
    return classify_pages(facts, expected_account_id, expected_currency)


def _monitor_targets(targets):
    # 已知挑战页优先，不访问其他验证码页。
    preferred = (
        select_existing_target(targets)
        if any(
            type(target) is dict
            and target.get("type") == "page"
            and urlsplit(target.get("url", "")).hostname in ALLOWED_HOSTS
            and urlsplit(target.get("url", "")).path
            in {"/security/twofactor/reauth", "/security/twofactor/reauth/"}
            for target in targets
        )
        else None
    )
    if preferred is not None:
        return [preferred]
    selected = [
        target
        for target in targets
        if type(target) is dict
        and target.get("type") == "page"
        and urlsplit(target.get("url", "")).scheme == "https"
        and urlsplit(target.get("url", "")).hostname in ALLOWED_HOSTS
    ]
    if not 1 <= len(selected) <= 20:
        raise ProbeError("IDENTITY_PROBE_FAILED")
    return sorted(selected, key=lambda value: value["targetId"])


async def observe_existing_pages(endpoint):
    """只绑定现有page target；CDP会话仅getTargets/attach/evaluate固定只读表达式/detach。"""
    from websockets.asyncio.client import connect
    from websockets.exceptions import WebSocketException

    endpoint = cdp_endpoint(endpoint)
    try:
        async with asyncio.timeout(8):
            async with connect(
                endpoint,
                proxy=None,
                open_timeout=3,
                close_timeout=1,
                max_size=262144,
                max_queue=4,
                compression=None,
            ) as websocket:
                sequence = 0

                async def command(method, params=None, session=None):
                    nonlocal sequence
                    sequence += 1
                    identifier = sequence
                    payload = {"id": identifier, "method": method, "params": params or {}}
                    if session is not None:
                        payload["sessionId"] = session
                    await websocket.send(json.dumps(payload))
                    for _ in range(100):
                        message = await websocket.recv()
                        if not isinstance(message, str) or len(message) > 262144:
                            raise ProbeError("CDP_UNAVAILABLE")
                        value = json.loads(message, object_pairs_hook=_unique_object)
                        if type(value) is not dict:
                            raise ProbeError("CDP_UNAVAILABLE")
                        if value.get("id") == identifier:
                            if "error" in value or type(value.get("result")) is not dict:
                                raise ProbeError("CDP_UNAVAILABLE")
                            return value["result"]
                    raise ProbeError("CDP_UNAVAILABLE")

                targets = (await command("Target.getTargets")).get("targetInfos")
                if type(targets) is not list or len(targets) > 100:
                    raise ProbeError("CDP_UNAVAILABLE")
                selected = _monitor_targets(targets)
                rounds = []
                for round_number in range(2):
                    if round_number:
                        await asyncio.sleep(0.15)
                    facts = []
                    for target in selected:
                        attached = await command(
                            "Target.attachToTarget",
                            {"targetId": target["targetId"], "flatten": True},
                        )
                        session = attached.get("sessionId")
                        if type(session) is not str:
                            raise ProbeError("CDP_UNAVAILABLE")
                        try:
                            result = await command(
                                "Runtime.evaluate",
                                {
                                    "expression": DOM_EXPRESSION_V2,
                                    "returnByValue": True,
                                    "awaitPromise": True,
                                    "silent": True,
                                    "timeout": 2000,
                                },
                                session,
                            )
                            if "exceptionDetails" in result:
                                raise ProbeError("IDENTITY_PROBE_FAILED")
                            facts.append(result.get("result", {}).get("value"))
                        finally:
                            await command("Target.detachFromTarget", {"sessionId": session})
                    rounds.append(facts)
                after = (await command("Target.getTargets")).get("targetInfos")
                if type(after) is not list or len(after) > 100:
                    raise ProbeError("CDP_UNAVAILABLE")
                if rounds[0] != rounds[1] or [(t["targetId"], t["url"]) for t in selected] != [
                    (t["targetId"], t["url"]) for t in _monitor_targets(after)
                ]:
                    raise ProbeError("IDENTITY_PROBE_FAILED")
                # 在进入按绑定判定前先验证事实结构，禁止任意DOM字段进入缓存。
                classify_pages(rounds[1], None, None)
                return rounds[1]
    except (TimeoutError, OSError, WebSocketException, ValueError, KeyError, TypeError):
        raise ProbeError("CDP_UNAVAILABLE") from None
