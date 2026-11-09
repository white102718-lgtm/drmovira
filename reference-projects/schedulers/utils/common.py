import logging
import re
import time
import traceback
from enum import Enum
from typing import TypedDict, List, Dict

from facebook_business.adobjects.adsinsights import AdsInsights

from db.clients import mongo_client, mongo_client_user

DayFormat = "%Y-%m-%d"
HourFormat = "%Y-%m-%d %H"
MinuteFormat = "%Y-%m-%d %H:%M"
SecondFormat = "%Y-%m-%d %H:%M:%S"


class Developer(TypedDict):
    access_token: str
    agent_lines: List[str]
    placer_id: str
    app_name: str
    ad_platform: str
    app_id: str
    app_secret: str
    date: str  # 中国时间
    dev_id: str
    status: int
    proxy: str
    review: bool


class DeveloperMsg(Developer):
    _id: str
    dev_mongo_id: str


class ProducerMsg(TypedDict):
    _id: str
    review: bool
    date: str
    type: str


class RunStatus(str, Enum):
    INVALID = "INVALID"
    ABORT = "ABORT"
    SENDING = "SENDING"
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    RETRY = "RETRY"
    FAILED = "FAILED"
    MANUAL = "MANUAL"
    DONE = [COMPLETED, FAILED]


class AdPlatform(str, Enum):
    GOOGLE = "google"
    FACEBOOK = "facebook"


class LEVEL(str, Enum):
    account = AdsInsights.Level.account
    campaign = AdsInsights.Level.campaign
    adset = AdsInsights.Level.adset
    ad = AdsInsights.Level.ad


def not_our_campaign(name: str, placer_id: str):
    id_lower = placer_id.lower()
    if id_lower not in name.lower().split("_"):
        return True


_LINE_SEP_RE = re.compile(r"[\s-]+")


def _clean_line_name(s: str) -> str:
    """归一化: 转小写, 空格/连字符统一成下划线。"""
    return _LINE_SEP_RE.sub("_", s.lower())


def build_line_index(agent_lines: List[str]) -> Dict[str, str]:
    """归一化线名 -> 原线名。归一化后重名的先到先得, 调用方按优先级排好序传入。"""
    index: Dict[str, str] = {}
    for line in agent_lines:
        c = _clean_line_name(line)
        if c:
            index.setdefault(c, line)
    return index


def build_line_maps(
    platform_lines: Dict[str, List[str]],
) -> tuple[Dict[str, str], Dict[str, str]]:
    """{game_platform: [lines]} -> (line->gp, 归一化线名索引)。同名线取先出现的平台。"""
    line_to_gp: Dict[str, str] = {}
    for gp, lines in platform_lines.items():
        for line in lines:
            line_to_gp.setdefault(line, gp)
    return line_to_gp, build_line_index(list(line_to_gp))


def get_line_from_campaign_name(name: str, line_index: Dict[str, str]) -> str | None:
    """系列名切 token 后枚举连续段查 line_index, 段长的优先, 同长取最左。

    等价于对每条线做 `"_线_" in "_系列名_"` 的归一化子串匹配,
    但耗时只随系列名长度增长, 与线的数量无关。
    """
    tokens = _clean_line_name(name).split("_")
    n = len(tokens)
    for span in range(n, 0, -1):
        for i in range(n - span + 1):
            line = line_index.get("_".join(tokens[i : i + span]))
            if line is not None:
                return line
    return None


def get_platform_lines(include_disabled: bool = False):
    query = {} if include_disabled else {"enabled": {"$ne": False}}
    plat_agents: List = list(
        mongo_client["platform_config"].find(
            query,
            {"agent_lines": 1, "_id": 1, "enabled": 1},
        )
    )
    # 启用平台排前: 归一化重名的线在 build_line_index 里先到先得, 让启用平台的优先
    plat_agents.sort(key=lambda item: item.get("enabled") is False)
    platform_lines = {item["_id"]: item.get("agent_lines", []) for item in plat_agents}
    return platform_lines


PLATFORM_LINES_CACHE_TTL = 600
_platform_lines_cache: tuple[float, Dict[str, List[str]]] | None = None


def get_platform_lines_cached() -> Dict[str, List[str]]:
    """全部平台(含禁用)的线表, 进程内缓存 PLATFORM_LINES_CACHE_TTL 秒。"""
    global _platform_lines_cache
    now = time.time()
    if _platform_lines_cache and now < _platform_lines_cache[0]:
        return _platform_lines_cache[1]
    data = get_platform_lines(include_disabled=True)
    _platform_lines_cache = (now + PLATFORM_LINES_CACHE_TTL, data)
    return data


def get_department_by_real_name(real_name: str) -> str | None:
    """根据用户 real_name 查询所属部门"""
    user_doc = mongo_client_user["user"].find_one(
        {"$or": [{"real_name": real_name}, {"full_name": real_name}]}, {"department": 1}
    )
    return user_doc.get("department") if user_doc else None


def get_placer_and_department(agent_line: str) -> tuple[str | None, str | None]:
    """根据代理线查询对应的优化师(placer_id)和所属部门"""
    agent_line_doc = mongo_client["agent_line_config"].find_one(
        {"_id": agent_line}, {"optimizer": 1}
    )
    if not agent_line_doc:
        return None, None
    optimizer = agent_line_doc.get("optimizer")
    if not optimizer:
        # 如果代理线没有投手，可能Mpower 代理线的确没有投手,就只有部门
        internal_team_doc = mongo_client["platform_config"].find_one(
            {"agent_lines": agent_line}, {"internal_team": 1}
        )
        internal_team = (internal_team_doc or {}).get("internal_team") or []
        return None, (internal_team[0] if internal_team else None)
    return optimizer, get_department_by_real_name(optimizer)


def url_variants(url: str) -> list[str]:
    """生成 URL 的等价变体（末尾斜杠、/? 与 ? 互换、URL编码/解码）"""
    from urllib.parse import quote, unquote

    if "?" in url:
        base, query = url.split("?", 1)
        query = "?" + query
    else:
        base, query = url, ""

    # 末尾斜杠变体
    bases = [base, base.rstrip("/")] if base.endswith("/") else [base, base + "/"]

    # query 编码/解码变体
    decoded_query = unquote(query)
    encoded_query = quote(decoded_query, safe="?&=")
    queries = {query, decoded_query, encoded_query}

    return list({b + q for b in bases for q in queries})


def get_game_platform_by_agent_line(agent_line: str) -> str | None:
    """通过 platform_config 反查 agent_line 所属的 game_platform"""
    doc = mongo_client["platform_config"].find_one(
        {"agent_lines": agent_line}, {"_id": 1}
    )
    return doc["_id"] if doc else None


def match_agent_line_by_url(
    objective: str | None,
    landing_url: str | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    """
    根据目标类型和投放链接匹配代理线。

    Returns:
        (agent_line, placer_id, department, game_platform)，未匹配到则全部为 None
    """
    if not objective or not landing_url:
        return None, None, None, None
    if objective.upper() not in {
        "OUTCOME_TRAFFIC",
        "OUTCOME_SALES",
        "OUTCOME_APP_PROMOTION",
    }:
        return None, None, None, None

    doc = mongo_client["agent_line_config"].find_one(
        {"history_package_urls": {"$in": url_variants(landing_url)}},
        {"_id": 1, "optimizer": 1},
    )
    if not doc:
        return None, None, None, None

    agent_line = doc["_id"]
    placer_id, department = get_placer_and_department(agent_line)
    game_platform = get_game_platform_by_agent_line(agent_line)
    return agent_line, placer_id, department, game_platform


class SyncHourCompleted(TypedDict):
    china_date: str
    game_platform: str
    agent_line: str
    ad_platform: str


def is_md5_format(hash_str: str) -> bool:
    if len(hash_str) != 8:
        return False
    pattern = re.compile(r"^[0-9a-f]+$", re.IGNORECASE)
    return bool(pattern.match(hash_str))


def is_valid_unique_name(name: str | None) -> bool:
    """unique_name 命名规则: 首字符 P(图片) 或 V(视频), 总长 9。

    规则来源: backend/tests/rename_files.py 的素材重命名规范。
    不符合规则的 ad_name 不应作为 unique_name 写入,
    应留 None 让 reuse_historical_unique_names / 素材抓取流程后续回填。
    """
    return bool(name) and len(name) == 9 and name[0] in ("P", "V")


def log_retry(retry_state):
    exception = retry_state.outcome.exception()
    format_exception = "".join(
        traceback.format_exception(type(exception), exception, exception.__traceback__)
    )
    logging.error(
        f"{retry_state.fn.__name__} 第 {retry_state.attempt_number} 次失败,"
        f"{retry_state.idle_for}秒后重试: {format_exception}",
    )


def set_local_proxy():
    import os

    if os.name == "nt":
        os.environ["HTTP_PROXY"] = "http://127.0.0.1:7897"
        os.environ["HTTPS_PROXY"] = "http://127.0.0.1:7897"


if __name__ == "__main__":
    # print(not_our_campaign("LY_jykx001_YGhy2_1029_apch", "ly"))
    # print(
    #     get_line_from_campaign_name(
    #         "57V_1134-FB-PWA-5_hedy_LB02_1029_apah", ["1134-Fb-PWA-5"]
    #     )
    # )
    # print(get_line_from_campaign_name("okclub-13235-11.20-dj", ["13235"]))
    # print(
    #     get_line_from_campaign_name(
    #         "come-nyc-12 - 广告副本 - 广告副本", ["come-nyc-12"]
    #     )
    # )
    # print(
    #     get_line_from_campaign_name("ly-Slot Lamp 777 Funn-423", ["Slot Lamp 777 Funn"])
    # )
    print(url_variants("https://link.lngjbg.com?bnp=gjwo&utm_act=5&utm_campaign={{campaign.name}}&utm_ad={{campaign.id}}&pixelid=1187035103179900"))
