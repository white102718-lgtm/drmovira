"""把广告在 FB 上的**原始素材文件名**拉回 mongo ad_asset_names,并从中还原本系统
素材名回写 doris。

处理两类广告:
  - `unique_name` 为空的广告,补上它用的图片/视频在 FB 素材库里的原始上传文件名;
  - `unique_name` 已被预览下载链路写入,且对应 materials.user 为 null 的广告。预览
    文件的字节可能被 FB 转码/压缩,下载后再算出来的 basename 不是原素材名,必须以 FB
    素材库中的原始上传文件名为准。

广告名自身以本系统素材名(P/V + 8 位 md5)开头时,即使后面带扩展名、尺寸或“广告副本”
等后缀,优先从广告名直接还原,不请求 FB。不碰 ad_config_ads —— 那张表是人工"查广告
配置"用的,两件事只是恰好都要读 creative,存储和字段各管各的。

原始文件名整体不符合 unique_name 的格式约束(P/V 开头共 9 位,见
utils.common.is_valid_unique_name),但**名字里常常嵌着**本系统素材名(前后带尺寸/
批次/扩展名,如 `P116d2368.jpg_105`)。抽得出来的就回写 doris,让看板只认
unique_name 一个 join 键;抽不出来的(FB 上直传、非本系统命名的素材)留在 mongo。
mongo 那份始终保留,是回写结果的溯源依据。

链路:
    doris ad_daily_detail 一条 SQL 拿窗口内 ad_name / unique_name 不一致的 ad
    → 广告名可解析的直接回写；空值或预览素材才继续下游
    → mongo _id 去重(ad_asset_names 自己就是去重表)
    → 按 dev 分组,dev 间并发 / dev 内串行,一个 dev 一个 API 实例
    → FB Batch API 拉 creative 的素材引用 → 账户边反查素材名
    → bulk_write 回写 mongo
    → 从素材名抽本系统素材名,回写 doris daily/hourly.unique_name

用法:
    python -m tasks.ad_materials.asset_name_sync             # 拉 FB + 回写 doris
    python -m tasks.ad_materials.asset_name_sync --backfill  # 只回写 doris,不打 FB
"""

import logging
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Iterator, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

from facebook_business.adobjects.adaccount import AdAccount
from pymongo import UpdateOne

from conf.api_conf import get_proxies
from conf.log_conf import init
from db.clients import mongo_client, mysql_client
from model_type_defs.ad_materials_type import AD_ASSET_NAME_COLLECTION
from utils.common_util import handle_error

from tasks.ad_sync_new.airbyte import API, fetch_ads_by_ids


logger = logging.getLogger(__name__)

_SHANGHAI = ZoneInfo("Asia/Shanghai")

# 只要素材引用,别的一律不拿。name/title/body/thumbnail_url/image_url/
# call_to_action_type 跟素材名无关(body 是广告正文,可以很长),ad 层的
# status/created_time/campaign_id 这些成效表里本来就有。
# object_story_spec 必须留:视频只有它里面的 video_id 在账户素材库 /advideos 里
# 查得到名字,creative.video_id 那个查不到(实测 0% 命中)。
# 待试:改成 creative{object_story_spec{video_data{video_id},link_data}} 能再小一个
# 数量级,但 FB 是否支持对这个 struct 做嵌套选择没验证过,别盲改。
AD_ASSET_FIELDS = [
    "id",
    "creative{image_hash,video_id,object_story_id,object_story_spec}",
]

# dev 间并发数;dev 内串行,一个 dev 一个 API 实例。
# 压到 4:本任务跟 ad_sync_new 成效同步共用同一批 app/token 配额(doris 的 dev_id 就是
# 成效那轮写的),回填期间实测 usage 冲到 84%,离 FB 开始拒绝很近。
DEV_CONCURRENCY = 4
ADS_PER_ROUND = 200       # 一轮处理多少 ad(fetch_ads_by_ids 内部再按 50 打 FB batch)
RETRY_BATCH_SIZE = 10     # 整批超时(FB code=960)后按更小的批重试,批小才不容易再超时
ASSET_LOOKUP_CHUNK = 50   # /adimages?hashes=[] 和 /advideos?filtering=[id IN] 的批大小
DEDUP_CHUNK = 1000        # mongo _id IN 去重的批大小
DORIS_WRITE_CHUNK = 500   # 回写 doris 时一批查/写多少个 ad
MAX_ATTEMPTS = 3          # 连续失败上限,超过不再拉
# 失败后多久才允许重试。没有它的话失败的 ad 每轮都回到候选里,连着占 MAX_ATTEMPTS 轮,
# 候选数一直下不来;拉长到一天一次,既让候选当轮就收敛,又保留对偶发失败的重试。
RETRY_COOLDOWN_HOURS = 24

# 默认窗口 = [今天-LOOKBACK_DAYS, 今天](中国日)。
# 不能只取当天:ad_daily_detail.date 是**账户本地日**,最西的户(UTC-9)本地日 L
# 要到中国日 L 的 17:00 才开始写行,当天只剩 7 次调度机会且没有第二次;回看一天
# 让每个 ad 多拿一整天的重试窗口。窗口只影响 doris/mongo 的扫描量,不影响 FB
# 调用量 —— 打 FB 的只有去重后剩下的。
LOOKBACK_DAYS = 1


def _chunks(items: List[Any], size: int) -> Iterator[List[Any]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


# ── Step 1: doris 候选集 ─────────────────────────────────────────────────────

def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _load_candidates(start_date: str, end_date: str) -> Dict[str, List[dict]]:
    """窗口内 ad_name 非空且与 unique_name 不一致的 ad,按 ad_id 归并。

    过滤走 `date`(UNIQUE KEY 第一列 = 排序键前缀,范围扫描),不用 china_date
    (非键列 + 该表无分区 = 全表扫)。同一 ad 跨天可能被不同 dev 拉过,全留着,
    后面挑第一个凭据可用的 dev。

    筛选口径:
      - ad_name 不能为空;
      - unique_name 为空,或与 ad_name 不相等。

    后续会再按来源分流:广告名可解析的直接回写;其余只对 unique_name 为空或当前
    unique_name 对应 materials.user 为 BSON null 的预览素材请求 FB。普通用户素材即使
    名称不同也不能覆盖。
    """
    sql = (
        "SELECT DISTINCT ad_id, account_id, account_name, dev_id, ad_name, unique_name "
        "FROM ad_daily_detail "
        f"WHERE level = 'ad' AND `date` >= '{start_date}' AND `date` <= '{end_date}' "
        "AND ad_id IS NOT NULL AND ad_id != '' "
        "AND ad_name IS NOT NULL AND TRIM(ad_name) != '' "
        "AND (unique_name IS NULL OR TRIM(unique_name) = '' "
        "OR TRIM(ad_name) != TRIM(unique_name))"
    )
    out: Dict[str, List[dict]] = defaultdict(list)
    seen: Set[str] = set()
    for ad_id, account_id, account_name, dev_id, ad_name, unique_name in mysql_client.read(sql):
        ad_id = str(ad_id)
        seen.add(ad_id)
        out[ad_id].append({
            "ad_id": ad_id,
            "account_id": str(account_id) if account_id else None,
            "account_name": account_name,
            "dev_id": str(dev_id) if dev_id else None,
            "ad_name": str(ad_name).strip(),
            "unique_name": str(unique_name).strip() if not _is_blank(unique_name) else None,
        })
    logger.warning(
        "[asset_name] 窗口 %s~%s ad_name 与 unique_name 不一致的 ad %d 个",
        start_date, end_date, len(seen),
    )
    return dict(out)


# ── Step 2: mongo 去重(ad_asset_names 自己就是去重表) ──────────────────────

def _drop_already_done(candidates: Dict[str, List[dict]]) -> Dict[str, List[dict]]:
    """本轮不再拉的三种:已经解析过的、连续失败到上限的、失败后还在冷却期的。

    注意 status=done 只表示"creative 拉到了、素材引用解析过了",不表示每个 name
    都非空 —— 主页帖子里的视频永远查不到名字,重试是白烧配额。以后真修好了那条路,
    用 assets.name=null 查出来单独补一次。
    """
    cooldown_until = datetime.now(timezone.utc) - timedelta(hours=RETRY_COOLDOWN_HOURS)
    skip: Set[str] = set()
    for chunk in _chunks(list(candidates), DEDUP_CHUNK):
        for doc in mongo_client[AD_ASSET_NAME_COLLECTION].find(
            {
                "_id": {"$in": chunk},
                "$or": [
                    {"status": "done"},
                    {"attempts": {"$gte": MAX_ATTEMPTS}},
                    {"attempts": {"$gt": 0}, "updated_at": {"$gt": cooldown_until}},
                ],
            },
            {"_id": 1},
        ):
            skip.add(doc["_id"])
    return {k: v for k, v in candidates.items() if k not in skip}


# ── Step 3: dev_id → FB 凭据 ────────────────────────────────────────────────

def _load_dev_credentials(dev_ids: Set[str]) -> Dict[str, dict]:
    """doris 行里的 dev_id 转 FB 凭据。

    两种形态:系统号 dev_id 就是 `accounts.dev_id`;个号是
    `"<企业dev_id>_<personal_accounts._id>"`,token 走个号、app_secret/proxy 走
    它 app_id 对应的 accounts 文档。凭据不全的 dev 不进结果。

    注:同类解析在 ad_config_worker._resolve_personal_token /
    ad_materials_sync._load_dev_fetch_configs / ad_sync_new.dispatcher._load_dev
    各有一份且口径不同,应当收口到一处,本次不动那三个在跑的服务。
    """
    system_ids = {d for d in dev_ids if "_" not in d}
    personal_ids = {d for d in dev_ids if "_" in d}
    out: Dict[str, dict] = {}

    if system_ids:
        for dev in mongo_client["accounts"].find(
            {"dev_id": {"$in": list(system_ids)}, "status": 1},
            {"dev_id": 1, "app_id": 1, "app_secret": 1, "access_token": 1, "proxy": 1},
        ):
            if all(dev.get(k) for k in ("app_id", "app_secret", "access_token", "proxy")):
                out[dev["dev_id"]] = {
                    "app_id": dev["app_id"],
                    "app_secret": dev["app_secret"],
                    "access_token": dev["access_token"],
                    "proxy": dev["proxy"],
                }

    if personal_ids:
        pid_to_dev = {d.split("_", 1)[1]: d for d in personal_ids}
        personals = list(mongo_client["personal_accounts"].find(
            {"_id": {"$in": list(pid_to_dev)}, "status": True},
            {"_id": 1, "app_id": 1, "access_token": 1},
        ))
        app_ids = {p["app_id"] for p in personals if p.get("app_id")}
        apps = {
            a["app_id"]: a
            for a in mongo_client["accounts"].find(
                {"app_id": {"$in": list(app_ids)}, "status": 1},
                {"app_id": 1, "app_secret": 1, "proxy": 1},
            )
        } if app_ids else {}
        for p in personals:
            app = apps.get(p.get("app_id"))
            dev_id = pid_to_dev.get(str(p["_id"]))
            if not dev_id or not p.get("access_token"):
                continue
            if not app or not app.get("app_secret") or not app.get("proxy"):
                continue
            out[dev_id] = {
                "app_id": p["app_id"],
                "app_secret": app["app_secret"],
                "access_token": p["access_token"],
                "proxy": app["proxy"],
            }

    return out


# ── 素材引用 + 素材名 ────────────────────────────────────────────────────────

def _collect_asset_refs(creative: Optional[dict]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """从 creative 刨出素材引用,返回 ({图片 hash: 引用来源}, {视频 id: 引用来源})。

    带引用来源是为了归类查不到名字的素材,不然只能猜。

    不收缩略图:`video_data.image_hash` 和 `asset_feed_spec.videos[].thumbnail_hash`
    是视频封面(见 publisher.py 的 `video_data["image_hash"] = thumb_hash`),
    收进来会让素材名里混进封面图。
    """
    hashes: Dict[str, str] = {}
    video_ids: Dict[str, str] = {}
    if not creative:
        return hashes, video_ids

    # 跑原帖广告:creative 直接引用已有主页帖子(publisher.py:479 那条路径传的就是
    # object_story_id),视频归 Page 所有,广告账户 token 查不到,整条 creative 的
    # 视频都不收。图片走账户边 /adimages,查不到只是空、不报错,照收。
    boosted_post = bool(creative.get("object_story_id"))

    def _add_video(video_id, source: str) -> None:
        if video_id and not boosted_post:
            video_ids.setdefault(str(video_id), source)

    if creative.get("image_hash"):
        hashes.setdefault(creative["image_hash"], "creative")

    spec = creative.get("object_story_spec") or {}
    link = spec.get("link_data") or {}
    if link.get("image_hash"):
        hashes.setdefault(link["image_hash"], "link_data")
    for child in link.get("child_attachments") or []:
        if child.get("image_hash"):
            hashes.setdefault(child["image_hash"], "child_attachments")
        _add_video(child.get("video_id"), "child_attachments")
    video_data = spec.get("video_data") or {}
    _add_video(video_data.get("video_id"), "video_data")

    # asset_feed_spec 当前不在 AD_ASSET_FIELDS 里(素材池大的广告疑似触发 FB code=1
    # "Please reduce the amount of data"),这段留着以便日后加回
    feed = creative.get("asset_feed_spec") or {}
    for image in feed.get("images") or []:
        if image.get("hash"):
            hashes.setdefault(image["hash"], "asset_feed")
    for video in feed.get("videos") or []:
        _add_video(video.get("video_id"), "asset_feed")

    # creative.video_id 只作兜底。实测同一条 creative 的 creative.video_id 和
    # object_story_spec.video_data.video_id 是两个不同的 id(数量恒定 1:1),而只有
    # video_data 那个在账户素材库 /advideos 里查得到名字,creative.video_id 一律查不到。
    # 别处已经拿到视频引用时就不收它,免得凭空多一条永远查不到名字的记录。
    if not video_ids:
        _add_video(creative.get("video_id"), "creative")

    return hashes, video_ids


class _AssetNameResolver:
    """hash / video_id → 素材原始文件名,按 dev 缓存(同一素材被多个广告共用很常见)。

    图片和视频都走账户边按 id 精确查,不读 /{id} 节点 —— 节点读视频会大面积
    code=10 (Permission denied),同一个 token 走账户边就没这问题。
    """

    def __init__(self, api: API):
        self._api = api
        self._image_names: Dict[str, Optional[str]] = {}
        self._video_names: Dict[str, Optional[str]] = {}

    def warm(
        self, account_id: str, hashes: Dict[str, str], video_ids: Dict[str, str],
    ) -> None:
        self._fetch_images(
            account_id, {h: s for h, s in hashes.items() if h not in self._image_names},
        )
        self._fetch_videos(account_id, video_ids)

    def assets(self, creative: Optional[dict]) -> List[dict]:
        hashes, video_ids = _collect_asset_refs(creative)
        return [
            {"type": "image", "id": h, "name": self._image_names.get(h)}
            for h in sorted(hashes)
        ] + [
            {"type": "video", "id": v, "name": self._video_names.get(v)}
            for v in sorted(video_ids)
        ]

    def _fetch_images(self, account_id: str, missing: Dict[str, str]) -> None:
        """/act_X/adimages 支持 hashes 参数按 id 过滤,所以只查要的,不用全列。"""
        for chunk in _chunks(list(missing), ASSET_LOOKUP_CHUNK):
            try:
                account = AdAccount(f"act_{account_id.removeprefix('act_')}", api=self._api.api)
                for image in account.get_ad_images(
                    fields=["hash", "name"], params={"hashes": chunk},
                ):
                    data = image.export_all_data()
                    if data.get("hash"):
                        self._image_names[data["hash"]] = data.get("name")
            except Exception as e:
                logger.warning(
                    "[asset_name] account=%s 查图片素材名失败 %d 个: %s",
                    account_id, len(chunk), e,
                )
            for h in chunk:
                self._image_names.setdefault(h, None)

    def _fetch_videos(self, account_id: str, refs: Dict[str, str]) -> None:
        """按 id 精确查,跟图片同一形状。

        `/advideos` 的 filtering 参数 SDK 参数表里没有(TypeChecker 只 warning 不拦
        请求),但实测生效。之前退而求其次列整库,一个素材库大的账户能把整个 dev
        卡住几十分钟,还白拉几千条用不上的记录。
        limit 卡在 chunk 大小:万一哪天 FB 不认 filtering 了,也不会退化成翻整库。
        查不到的留 None —— 主页帖子里的视频归 Page 所有,这个 token 够不着。
        """
        missing = {v: s for v, s in refs.items() if v not in self._video_names}
        if not missing:
            return
        act = f"act_{account_id.removeprefix('act_')}"
        for chunk in _chunks(list(missing), ASSET_LOOKUP_CHUNK):
            try:
                for video in AdAccount(act, api=self._api.api).get_ad_videos(
                    fields=["id", "title"],
                    params={
                        "filtering": [
                            {"field": "id", "operator": "IN", "value": chunk},
                        ],
                        "limit": len(chunk),
                        "summary": "false",
                    },
                ):
                    data = video.export_all_data()
                    if data.get("id"):
                        self._video_names[str(data["id"])] = data.get("title")
            except Exception as e:
                logger.warning(
                    "[asset_name] account=%s 查视频素材名失败 %d 个: %s",
                    account_id, len(chunk), e,
                )
            for vid in chunk:
                self._video_names.setdefault(vid, None)

        unresolved = [v for v in missing if not self._video_names.get(v)]
        if unresolved:
            logger.info(
                "[asset_name] account=%s 视频素材名 %d/%d 个没查到,按引用来源 %s",
                account_id, len(unresolved), len(missing),
                dict(Counter(missing[v] for v in unresolved)),
            )


# ── 回写 mongo ───────────────────────────────────────────────────────────────

def _done_op(row: dict, assets: List[dict], now: datetime) -> UpdateOne:
    return UpdateOne(
        {"_id": row["ad_id"]},
        {
            "$set": {
                "account_id": row["account_id"],
                "account_name": row["account_name"],
                "assets": assets,
                "status": "done",
                "error": None,
                "attempts": 0,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )


def _failed_ops(rows: Iterable[dict], error: str, now: datetime) -> List[UpdateOne]:
    return [
        UpdateOne(
            {"_id": row["ad_id"]},
            {
                "$set": {
                    "account_id": row["account_id"],
                    "account_name": row["account_name"],
                    "status": "failed",
                    "error": error,
                    "updated_at": now,
                },
                "$inc": {"attempts": 1},
                "$setOnInsert": {"assets": [], "created_at": now},
            },
            upsert=True,
        )
        for row in rows
    ]


def _flush(ops: List[UpdateOne]) -> None:
    if ops:
        mongo_client[AD_ASSET_NAME_COLLECTION].bulk_write(ops, ordered=False)


# ── 回写 doris unique_name ──────────────────────────────────────────────────

# 本系统素材名 = P(图片)/V(视频) + 文件 md5 前 8 位小写十六进制
# (backend material_order_service._process_one_media 的 object_key 规则)
_BASENAME_RE = re.compile(r"[PV][0-9a-f]{8}")


def _basename_from_ad_name(ad_name: Optional[str]) -> Optional[str]:
    """广告名以素材名开头时直接取它,允许后面跟扩展名、尺寸、广告副本等后缀。"""
    if not isinstance(ad_name, str):
        return None
    matched = _BASENAME_RE.match(ad_name.strip())
    return matched.group(0) if matched else None


def _preview_basenames(candidates: Dict[str, List[dict]]) -> Set[str]:
    """返回候选中来自预览下载链路的 basename。

    backend 对预览下载素材写入 BSON null 的 user；这里刻意使用 $type: 10，严格只匹配
    null，不把字段缺失或空字符串误判为预览素材。
    """
    names = {
        row["unique_name"]
        for rows in candidates.values()
        for row in rows
        if not _is_blank(row.get("unique_name"))
    }
    preview: Set[str] = set()
    for chunk in _chunks(list(names), DEDUP_CHUNK):
        for doc in mongo_client["materials"].find(
            {"basename": {"$in": chunk}, "user": {"$type": 10}},
            {"basename": 1},
        ):
            if doc.get("basename"):
                preview.add(str(doc["basename"]))
    return preview


def _route_candidates(
    candidates: Dict[str, List[dict]],
) -> Tuple[Dict[str, str], Dict[str, List[dict]], Set[str]]:
    """将候选分成广告名可直接还原和必须查 FB 的两类。

    返回 (广告名直接回写映射, 待查 FB 的行, 已被预览素材错误写入的 ad_id)。
    同一 ad 有多个历史广告名且解析出多个素材名时不猜，走 FB 路径（若它是预览/空值）。
    """
    preview_basenames = _preview_basenames(candidates)
    direct: Dict[str, str] = {}
    pending: Dict[str, List[dict]] = {}
    preview_ad_ids: Set[str] = set()
    skipped_non_preview = 0

    for ad_id, rows in candidates.items():
        ad_name_basenames = {
            basename
            for row in rows
            if (basename := _basename_from_ad_name(row.get("ad_name")))
        }
        if len(ad_name_basenames) == 1:
            basename = ad_name_basenames.pop()
            # 目标已经正确时不做重复写入；广告名有后缀仍会进入候选 SQL，故这里必需。
            if any(row.get("unique_name") != basename for row in rows):
                direct[ad_id] = basename
            continue
        if len(ad_name_basenames) > 1:
            logger.warning(
                "[asset_name] ad=%s 历史广告名解析出多个素材名 %s，不按广告名直接回写",
                ad_id, sorted(ad_name_basenames),
            )

        rows_needing_fb = []
        for row in rows:
            unique_name = row.get("unique_name")
            if _is_blank(unique_name):
                rows_needing_fb.append(row)
            elif unique_name in preview_basenames:
                rows_needing_fb.append(row)
                preview_ad_ids.add(ad_id)
            else:
                skipped_non_preview += 1
        if rows_needing_fb:
            pending[ad_id] = rows_needing_fb

    logger.warning(
        "[asset_name] 分流: 广告名直接回写 %d 个, 预览/空值待查 FB %d 个, "
        "普通素材行跳过 %d 条",
        len(direct), len(pending), skipped_non_preview,
    )
    return direct, pending, preview_ad_ids


def _basename_from_assets(assets: Optional[List[dict]]) -> Optional[str]:
    """从 FB 原始素材文件名里抽本系统素材名。一条广告抽出多个时不猜归属,返回 None。"""
    found = {
        m.group(0)
        for a in assets or []
        if isinstance(a, dict) and isinstance(a.get("name"), str)
        for m in _BASENAME_RE.finditer(a["name"])
    }
    return found.pop() if len(found) == 1 else None


def _keep_existing(by_ad_id: Dict[str, str]) -> Dict[str, str]:
    """丢掉素材库和工单产出物里都查不到的名字。FB 上的文件名碰巧长成这个形状不代表
    是本系统素材,错回写会把消耗归到一个不存在的素材上。"""
    wanted = list(set(by_ad_id.values()))
    alive: Set[str] = set()
    for chunk in _chunks(wanted, DEDUP_CHUNK):
        alive.update(mongo_client["materials"].distinct(
            "basename", {"basename": {"$in": chunk}}))
    for chunk in _chunks([b for b in wanted if b not in alive], DEDUP_CHUNK):
        alive.update(mongo_client["material_order_outputs"].distinct(
            "basename", {"basename": {"$in": chunk}}))
    return {ad_id: b for ad_id, b in by_ad_id.items() if b in alive}


def _sql_value(value: Any) -> str:
    return "'%s'" % str(value).replace("\\", "\\\\").replace("'", "\\'")


def _write_unique_names(
    by_ad_id: Dict[str, str], overwrite_ad_ids: Optional[Set[str]] = None,
) -> int:
    """按 ad_id 回写 daily 与 hourly 的 unique_name（Doris 部分列更新）。

    默认只补空值；`overwrite_ad_ids` 仅用于两种已确认需要纠错的广告：
    广告名直接解析出的素材名，或当前 unique_name 命中 materials.user 为 BSON null 的
    预览素材。这样不会覆盖正常用户上传素材的 unique_name。

    不限日期，同一 ad 的历史行一并补齐。hourly 也同步修正，避免错误的预览素材名被
    reuse_historical_unique_names 再传播到其他记录。
    """
    if not by_ad_id:
        return 0
    overwrite_ad_ids = overwrite_ad_ids or set()
    written = 0
    with mysql_client.session() as cur:
        cur.execute("SET enable_unique_key_partial_update = true")
        cur.execute("SET enable_insert_strict = false")
        for table_name in ("ad_daily_detail", "ad_hourly_detail"):
            for chunk in _chunks(list(by_ad_id), DORIS_WRITE_CHUNK):
                ids = ", ".join(_sql_value(ad_id) for ad_id in chunk)
                cur.execute(
                    "SELECT `date`, ad_platform, timezone_name, account_id, campaign_id, "
                    f"ad_set_id, ad_id, unique_name FROM {table_name} "
                    f"WHERE level = 'ad' AND ad_id IN ({ids})"
                )
                values = []
                for row in cur.fetchall():
                    *primary_key, ad_id, old_unique_name = row
                    new_unique_name = by_ad_id[str(ad_id)]
                    should_write = _is_blank(old_unique_name) or (
                        str(ad_id) in overwrite_ad_ids and old_unique_name != new_unique_name
                    )
                    # 主键列缺值的行按等值匹配不上，且目标已正确的行无需重复写。
                    if should_write and all(value is not None for value in primary_key + [ad_id]):
                        values.append(
                            "(%s)" % ", ".join(
                                _sql_value(value) for value in (*primary_key, ad_id, new_unique_name)
                            )
                        )
                if not values:
                    continue
                cur.execute(
                    f"INSERT INTO {table_name} (date, ad_platform, timezone_name, "
                    "account_id, campaign_id, ad_set_id, ad_id, unique_name) VALUES "
                    + ", ".join(values)
                )
                written += len(values)
    return written


@handle_error(error_message="素材名回写 doris 失败")
def backfill_unique_names(overwrite_ad_ids: Optional[Set[str]] = None) -> int:
    """把 ad_asset_names 里已解析出的原始素材名还原成本系统素材名,回写 doris。

    每轮全量扫,不只处理本轮新增:上一轮写失败的下轮自动重来。默认只补空值；本轮
    已确认是预览素材的广告则纠正其现有值。
    """
    by_ad_id = {
        str(doc["_id"]): basename
        for doc in mongo_client[AD_ASSET_NAME_COLLECTION].find(
            {"status": "done"}, {"assets.name": 1}
        )
        if (basename := _basename_from_assets(doc.get("assets")))
    }
    alive = _keep_existing(by_ad_id)
    written = _write_unique_names(alive, overwrite_ad_ids)
    logger.warning(
        "[asset_name] 回写 doris:抽出素材名的 ad %d 个,其中素材真实存在 %d 个,写入 %d 行",
        len(by_ad_id), len(alive), written,
    )
    return written


# ── Step 4: 单 dev 拉取 ──────────────────────────────────────────────────────

def _fetch_creatives(account_id: str, ad_ids: List[str], api: API) -> Dict[str, dict]:
    ads = fetch_ads_by_ids(
        {"account_id": account_id}, ad_ids, fields=AD_ASSET_FIELDS, api=api,
    )
    return {str(a["id"]): a for a in ads if a.get("id")}


def _sync_one_dev(
    dev_id: str, creds: dict, ads_by_account: Dict[str, List[dict]],
) -> Tuple[int, int]:
    # API() 会 set_default_api(),多线程下互相覆盖全局默认;本函数所有 FB 调用都
    # 显式带 api=,不走全局默认,才是线程安全的。新增调用时别漏 api=。
    api = API(
        app_id=creds["app_id"],
        app_secret=creds["app_secret"],
        access_token=creds["access_token"],
        proxies=get_proxies(creds["proxy"]),
    )
    resolver = _AssetNameResolver(api)
    ok = fail = 0

    for account_id, rows in ads_by_account.items():
        by_id = {row["ad_id"]: row for row in rows}
        for chunk in _chunks(list(by_id), ADS_PER_ROUND):
            now = datetime.now(timezone.utc)
            try:
                creatives = _fetch_creatives(account_id, chunk, api)
            except Exception as e:
                logger.error(
                    "[asset_name][%s] account=%s 拉取失败 %d 个: %s",
                    dev_id, account_id, len(chunk), e, exc_info=True,
                )
                _flush(_failed_ops([by_id[a] for a in chunk], str(e), now))
                fail += len(chunk)
                continue

            # FB code=960 是"整批超时"(整批共一个 fbtrace_id),跟对象本身没关系。
            # 直接记 failed 会让 attempts 攒满、把 ad 永久拉黑,先用小批重试一次。
            retry_ids = [a for a in chunk if a not in creatives]
            if retry_ids:
                for small in _chunks(retry_ids, RETRY_BATCH_SIZE):
                    try:
                        creatives.update(_fetch_creatives(account_id, small, api))
                    except Exception as e:
                        logger.warning(
                            "[asset_name][%s] account=%s 小批重试失败 %d 个: %s",
                            dev_id, account_id, len(small), e,
                        )
                recovered = len(retry_ids) - len([a for a in chunk if a not in creatives])
                logger.info(
                    "[asset_name][%s] account=%s 小批重试 %d 个,救回 %d 个",
                    dev_id, account_id, len(retry_ids), recovered,
                )

            hashes: Dict[str, str] = {}
            video_ids: Dict[str, str] = {}
            for ad in creatives.values():
                h, v = _collect_asset_refs(ad.get("creative"))
                for ref, source in h.items():
                    hashes.setdefault(ref, source)
                for ref, source in v.items():
                    video_ids.setdefault(ref, source)
            resolver.warm(account_id, hashes, video_ids)

            ops: List[UpdateOne] = []
            fetched: Set[str] = set()
            for ad_id, ad in creatives.items():
                row = by_id.get(ad_id)
                if not row:
                    continue
                fetched.add(ad_id)
                ops.append(_done_op(row, resolver.assets(ad.get("creative")), now))
            missing = [by_id[a] for a in chunk if a not in fetched]
            ops += _failed_ops(missing, "FB 未返回该广告(已删除或无权限)", now)
            _flush(ops)
            ok += len(fetched)
            fail += len(missing)

    logger.info("[asset_name][%s] 完成 成功=%d 失败=%d", dev_id, ok, fail)
    return ok, fail


# ── 主入口 ───────────────────────────────────────────────────────────────────

@handle_error(error_message="FB 素材名同步失败")
def _fetch_asset_names(
    start_date: Optional[str] = None, end_date: Optional[str] = None,
) -> Set[str]:
    """处理窗口内 ad_name/unique_name 不一致的广告，返回需要覆盖旧值的预览 ad_id。"""
    today = datetime.now(_SHANGHAI).date()
    start_date = start_date or (today - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    end_date = end_date or today.strftime("%Y-%m-%d")

    candidates = _load_candidates(start_date, end_date)
    direct_by_ad_id, fb_candidates, preview_ad_ids = _route_candidates(candidates)
    direct_written = _write_unique_names(direct_by_ad_id, set(direct_by_ad_id))
    if direct_by_ad_id:
        logger.warning(
            "[asset_name] 从广告名直接回写: ad %d 个, daily/hourly 共写入 %d 行",
            len(direct_by_ad_id), direct_written,
        )

    pending = _drop_already_done(fb_candidates)
    logger.warning(
        "[asset_name] 窗口 %s~%s FB 候选 %d 个 ad,去重后待拉 %d 个",
        start_date, end_date, len(fb_candidates), len(pending),
    )
    if not pending:
        return preview_ad_ids

    dev_ids = {row["dev_id"] for rows in pending.values() for row in rows if row["dev_id"]}
    creds = _load_dev_credentials(dev_ids)

    # dev_id -> account_id -> [row];同一 ad 跨天可能挂不同 dev,挑第一个凭据可用的
    grouped: Dict[str, Dict[str, List[dict]]] = defaultdict(lambda: defaultdict(list))
    orphans: List[dict] = []
    for rows in pending.values():
        row = next((r for r in rows if r["dev_id"] in creds and r["account_id"]), None)
        if row is None:
            orphans.append(rows[0])
            continue
        grouped[row["dev_id"]][row["account_id"]].append(row)

    if orphans:
        logger.warning("[asset_name] %d 个 ad 没有可用开发者凭据,记失败", len(orphans))
        _flush(_failed_ops(orphans, "无可用开发者凭据", datetime.now(timezone.utc)))

    total_ok, total_fail = 0, len(orphans)
    with ThreadPoolExecutor(max_workers=DEV_CONCURRENCY, thread_name_prefix="assetname") as pool:
        futures = {
            pool.submit(_sync_one_dev, dev_id, creds[dev_id], by_account): dev_id
            for dev_id, by_account in grouped.items()
        }
        for future in as_completed(futures):
            dev_id = futures[future]
            try:
                ok, fail = future.result()
            except Exception as e:
                logger.error("[asset_name][%s] 整 dev 失败: %s", dev_id, e, exc_info=True)
                continue
            total_ok += ok
            total_fail += fail

    logger.warning(
        "[asset_name] 结束 dev=%d 成功=%d 失败=%d", len(grouped), total_ok, total_fail,
    )
    return preview_ad_ids


def sync_fb_asset_names(
    start_date: Optional[str] = None, end_date: Optional[str] = None,
) -> None:
    """调度入口(tasks/main.py 的 fb_asset_name_sync 作业)：拉 FB 素材名落 mongo，
    再把名字里嵌的本系统素材名回写 daily/hourly doris。

    默认窗口见 LOOKBACK_DAYS。历史回填传 start_date / end_date 手动分段跑。
    两步各自吞异常：拉取失败也要回写，上一轮写失败的靠这轮补上。
    """
    preview_ad_ids = _fetch_asset_names(start_date, end_date) or set()
    backfill_unique_names(preview_ad_ids)


if __name__ == "__main__":
    init("asset_name_sync")
    # --backfill:只把已经拉回来的素材名回写 doris,不打 FB(历史回填/重试用)
    if "--backfill" in sys.argv:
        today = datetime.now(_SHANGHAI).date()
        start_date = (today - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
        candidates = _load_candidates(start_date, end_date)
        direct_by_ad_id, _, preview_ad_ids = _route_candidates(candidates)
        _write_unique_names(direct_by_ad_id, set(direct_by_ad_id))
        backfill_unique_names(preview_ad_ids)
    else:
        sync_fb_asset_names()
