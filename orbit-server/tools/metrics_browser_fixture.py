"""原Metrics公开HTTP/浏览器的隔离技术夹具；不是Meta采集或生产发行者。

本模块只供显式ORBIT_PYTHON_TEST_METRICS_BROWSER=True的隔离child导入。
父进程先完成独立SQL登记，再以原子控制文件提供白名单定位信息。
"""

import asyncio
import itertools
import json
import re
from datetime import UTC, date
from pathlib import Path
from uuid import UUID, uuid4

from metric_fact_schema_checks import MetricFactSqlFixture, digest
from metric_profile_query_checks import seed_metric_profile_browser_fixture
from metrics_query_read_checks import RegisteredSqlReadSource, guard_target
from metrics_query_result_checks import (
    RegisteredSqlExpected,
    encode_manifest,
    query,
    stream_hash,
)
from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.metrics_query_result_contract import (
    ExpectedEntityMembership,
    ExpectedUnitManifest,
    ExpectedUnitProvider,
    ExpectedUnitReceipt,
    QuerySourceIdentity,
)
from orbit_api.metrics_query_store import (
    MetricReadSourceProvider,
    metric_query_hash,
    publication_validation_binding,
)
from orbit_api.metrics_scope_access import authorize_metric_scope

CONTROL_ROOT = Path(__file__).resolve().parents[1] / ".runtime" / "metrics-browser-fixture"
CONTROL_KEYS = {"version", "run_id", "database", "tenant_id", "read_registry", "expected_registry"}
DATASETS = ("ACCOUNT", "CAMPAIGN", "ADSET", "AD")
SORTS = ("spend", "impressions", "clicks", "purchases", "roas", "cpm", "name")
Q_VALUES = ("", "中文", "%_!", "不存在的指标")


def unavailable():
    raise OrbitError(503, "METRICS_DATA_UNVERIFIED", "指标测试来源尚未就绪") from None


def exact_uuid(value):
    if type(value) is not str:
        unavailable()
    try:
        if str(UUID(value)) != value:
            unavailable()
    except (ValueError, AttributeError):
        unavailable()
    return value


def control_path(value):
    if type(value) not in {str, Path}:
        # WindowsPath是Path具体子类，调用方也可传原字符串。
        if not isinstance(value, Path):
            unavailable()
    original = Path(value)
    if not original.is_absolute():
        unavailable()
    for part in (original, *original.parents):
        if part.is_symlink() or (getattr(part, "is_junction", lambda: False)()):
            unavailable()
    resolved = original.resolve()
    if resolved.name != "control.json" or resolved.parent.parent != CONTROL_ROOT.resolve():
        unavailable()
    exact_uuid(resolved.parent.name)
    return resolved


def validate_control(value, path):
    if (
        type(value) is not dict
        or set(value) != CONTROL_KEYS
        or type(value["version"]) is not int
        or value["version"] != 1
    ):
        unavailable()
    exact_uuid(value["run_id"])
    exact_uuid(value["tenant_id"])
    if value["run_id"] != path.parent.name:
        unavailable()
    for key, pattern in (
        ("database", r"orbit_py_it_[a-f0-9]{32}"),
        ("read_registry", r"it_metric_read_[a-f0-9]{16}"),
        ("expected_registry", r"it_metric_expect_[a-f0-9]{16}"),
    ):
        if type(value[key]) is not str or re.fullmatch(pattern, value[key]) is None:
            unavailable()
    return dict(value)


def load_control(value):
    path = control_path(value)
    try:
        with path.open("rb") as stream:
            encoded = stream.read(4097)
        if len(encoded) > 4096:
            unavailable()

        def unique(pairs):
            result = {}
            for key, item in pairs:
                if key in result:
                    raise ValueError("重复控制字段")
                result[key] = item
            return result

        return validate_control(json.loads(encoded.decode("utf-8"), object_pairs_hook=unique), path)
    except (OSError, ValueError, UnicodeError, TypeError):
        unavailable()


class _LazyControl:
    def __init__(self, path=None, *, enabled=False):
        self.path, self.enabled, self.saved = path, enabled, None

    async def require(self, session, scope):
        # 未显式测试开关/无文件先0SQL拒绝；不能仅凭一个kind标签激活技术来源。
        if self.enabled is not True or self.path is None:
            unavailable()
        if self.saved is None:
            self.saved = load_control(self.path)
        value = self.saved
        if scope.current.tenant_id != value["tenant_id"]:
            unavailable()
        bind = getattr(session, "bind", None)
        url = getattr(bind, "url", None) or getattr(getattr(bind, "engine", None), "url", None)
        if (
            url is None
            or url.host != "127.0.0.1"
            or url.port != 13306
            or url.database != value["database"]
        ):
            unavailable()
        actual = (await session.execute(text("SELECT DATABASE()"))).scalar_one()
        if actual != value["database"]:
            unavailable()
        return value


class LazyMetricsReadProvider(MetricReadSourceProvider):
    kind = "ISOLATED_TEST"

    def __init__(self, control=None, *, enabled=False):
        self.control = _LazyControl(control, enabled=enabled)
        self.delegate = None

    async def verify_publications(self, session, scope, original_query, heads):
        value = await self.control.require(session, scope)
        if self.delegate is None:
            self.delegate = RegisteredSqlReadSource(value["read_registry"])
        return await self.delegate.verify_publications(session, scope, original_query, heads)


class LazyMetricsExpectedProvider(ExpectedUnitProvider):
    kind = "ISOLATED_TEST"

    def __init__(self, control=None, *, enabled=False):
        self.control = _LazyControl(control, enabled=enabled)
        self.delegate = None

    async def _delegate(self, session, scope):
        value = await self.control.require(session, scope)
        if self.delegate is None:
            self.delegate = RegisteredSqlExpected(value["expected_registry"])
        return self.delegate

    async def prepare_manifest(self, session, scope, query_body, source):
        return await (await self._delegate(session, scope)).prepare_manifest(
            session, scope, query_body, source
        )

    async def revalidate_manifest(self, session, scope, query_body, manifest):
        return await (await self._delegate(session, scope)).revalidate_manifest(
            session, scope, query_body, manifest
        )

    async def iter_unit_batches(self, session, scope, query_body, manifest):
        delegate = await self._delegate(session, scope)
        async for batch in delegate.iter_unit_batches(session, scope, query_body, manifest):
            yield batch

    async def iter_membership_batches(self, session, scope, query_body, manifest):
        delegate = await self._delegate(session, scope)
        async for batch in delegate.iter_membership_batches(session, scope, query_body, manifest):
            yield batch


def supported_queries(profile_id):
    # 仅事先登记的有限技术查询，Provider不根据传入任意query即时制造完整性证明。
    for dataset, size, granularity, sort, direction in itertools.product(
        DATASETS, (20, 50, 100, 200), ("SUMMARY", "DAY"), SORTS, ("ASC", "DESC")
    ):
        yield query(
            profile_id,
            dataset=dataset,
            page_size=size,
            granularity=granularity,
            sort=sort,
            direction=direction,
        )
    for q, size in itertools.product(Q_VALUES[1:], (20, 50, 100, 200)):
        yield query(profile_id, q=q, page_size=size)


def expected_streams(fixture, profile, trees, ads, renamed, body):
    units, memberships = [], []
    kind = body["dataset"]
    for account_index, tree in enumerate(trees):
        for day_text in (body["date_from"], body["date_to"]):
            if account_index == 0:
                dimensions = (
                    ads if kind == "AD" else [tree[{"ACCOUNT": 0, "CAMPAIGN": 1, "ADSET": 2}[kind]]]
                )
            elif account_index == 1 and kind != "ACCOUNT":
                dimensions = []
            else:
                dimensions = [tree[{"ACCOUNT": 0, "CAMPAIGN": 1, "ADSET": 2, "AD": 3}[kind]]]
            selected = []
            for dimension in dimensions:
                latest = (
                    renamed
                    if account_index == 0
                    and kind == "AD"
                    and dimension["entity_id"] == ads[0]["entity_id"]
                    else dimension
                )
                if (
                    body["q"]
                    and body["q"] not in latest["name"]
                    and not (body["q"].isdigit() and body["q"] == latest["external_id"])
                ):
                    continue
                name = renamed if latest is renamed and day_text.endswith("02") else dimension
                selected.append(
                    ExpectedEntityMembership(
                        fixture.tenant,
                        tree[0]["account_id"],
                        date.fromisoformat(day_text),
                        profile["id"],
                        profile["version"],
                        kind,
                        name["entity_id"],
                        name["id"],
                        120,
                        fixture.now.replace(tzinfo=UTC),
                    )
                )
            selected.sort(key=lambda item: item.key())
            memberships.extend(selected)
            units.append(
                ExpectedUnitReceipt(
                    fixture.tenant,
                    tree[0]["account_id"],
                    date.fromisoformat(day_text),
                    profile["id"],
                    profile["version"],
                    fixture.owner,
                    fixture.team,
                    ("USD", "EUR", "GBP")[account_index],
                    "Asia/Shanghai",
                    tree[0]["id"],
                    1,
                    len(selected),
                    stream_hash(selected),
                )
            )
    return tuple(sorted(units, key=lambda item: item.key())), tuple(
        sorted(memberships, key=lambda item: item.key())
    )


def create_registered_publication(fixture, profile, configuration):
    # 048 intent guard从INSERT起冻结来源身份，不能先空来源再UPDATE补签。
    return fixture.insert(
        "orbit_metric_publication",
        {
            "tenant_id": fixture.tenant,
            "id": str(uuid4()),
            "profile_id": profile["id"],
            "profile_version": profile["version"],
            "profile_hash": digest(profile),
            "authority_kind": "ISOLATED_TEST",
            "source_config_id": configuration,
            "source_config_revision": 1,
            "source_proof_json": '{"kind":"SQL_ONLY_NOT_PLATFORM"}',
            "expected_cell_count": 4,
            "expected_cells_hash": "a" * 64,
            "capture_sequence_max": 120,
            "publisher_actor_id": 1,
            "request_id": str(uuid4()),
            "created_at": fixture.now,
        },
    )


def prepare_metrics_browser_fixture(client, admin, headers, password, cache, database):
    """父进程调用；返回安全定位和预期集合，不写控制文件、不启动服务/浏览器。"""
    guard_target(admin, database)
    from config.asyncmy_compat import install_windows_asyncmy_compat

    install_windows_asyncmy_compat()
    fixture = MetricFactSqlFixture(admin, database)
    profile = seed_metric_profile_browser_fixture(admin, database)["profiles"][0]
    sql = fixture.sql
    read_registry = "it_metric_read_" + uuid4().hex[:16]
    expected_registry = "it_metric_expect_" + uuid4().hex[:16]
    sql(
        "CREATE TABLE "
        + read_registry
        + "(tenant_id CHAR(36) NOT NULL,publication_id CHAR(36) NOT NULL,"
        "binding_json JSON NOT NULL,binding_hash CHAR(64) NOT NULL,"
        "revoked TINYINT NOT NULL DEFAULT 0,"
        "PRIMARY KEY(tenant_id,publication_id)) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs"
    )
    sql(
        "CREATE TABLE "
        + expected_registry
        + "(tenant_id CHAR(36) NOT NULL,actor_id BIGINT NOT NULL,"
        "query_hash CHAR(64) NOT NULL,source_id CHAR(36) NOT NULL,body_json JSON NOT NULL,"
        "body_hash CHAR(64) NOT NULL,revoked TINYINT NOT NULL DEFAULT 0,"
        "PRIMARY KEY(tenant_id,actor_id,query_hash,source_id)) "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs"
    )
    configuration = str(uuid4())
    sql(
        "INSERT INTO orbit_system_configuration(id,tenant_id,section,name,enabled,"
        "settings_json,secrets_json) "
        "VALUES(%s,%s,'METRICS',%s,1,'{}','{}')",
        (configuration, fixture.tenant, "BROWSER_SQL_" + uuid4().hex[:12]),
    )
    accounts = [fixture.account() for _ in range(3)]
    trees = [fixture.tree(account) for account in accounts]
    for account, currency in zip(accounts, ("USD", "EUR", "GBP"), strict=True):
        sql(
            "UPDATE orbit_ad_account SET currency=%s WHERE tenant_id=%s AND id=%s",
            (currency, fixture.tenant, account),
        )
    ads = [trees[0][3]] + [
        fixture.dimension(accounts[0], "AD", parent=trees[0][2], name=f"中文指标广告{index:02}")
        for index in range(1, 21)
    ]
    renamed = dict(ads[0]) | {"id": str(uuid4()), "name": "中文指标名称%_!"}
    renamed["content_hash"] = digest(
        {key: value for key, value in renamed.items() if key not in {"id", "content_hash"}}
    )
    fixture.insert("orbit_metric_entity_snapshot", renamed)
    publication = create_registered_publication(fixture, profile, configuration)
    for day in ("2026-01-01", "2026-01-02"):
        cell = fixture.cell(publication, trees[0], day=day)
        sql(
            "UPDATE orbit_metric_capture_cell SET expected_entity_count=21,fact_count=21 "
            "WHERE tenant_id=%s AND id=%s",
            (fixture.tenant, cell["id"]),
        )
        for index, ad in enumerate(ads):
            chosen = renamed if index == 0 and day.endswith("02") else ad
            fixture.fact(cell, trees[0][:3] + [chosen])
        empty = fixture.cell(publication, trees[1], day=day, empty=True)
        sql(
            "UPDATE orbit_metric_capture_cell SET currency='EUR' WHERE tenant_id=%s AND id=%s",
            (fixture.tenant, empty["id"]),
        )
    generation = fixture.publish(publication, facts=42)
    with admin.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM orbit_metric_publication WHERE tenant_id=%s AND id=%s",
            (fixture.tenant, publication["id"]),
        )
        head = dict(
            zip((column[0] for column in cursor.description), cursor.fetchone(), strict=True)
        )
    admin.commit()
    binding = publication_validation_binding(head)
    sql(
        "INSERT INTO " + read_registry + " VALUES(%s,%s,%s,%s,0)",
        (fixture.tenant, publication["id"], canonical(binding), digest(binding)),
    )

    async def register():
        engine = create_async_engine(
            URL.create(
                "mysql+asyncmy",
                username="root",
                password="",
                host="127.0.0.1",
                port=13306,
                database=database,
            ),
            echo=False,
            hide_parameters=True,
        )
        try:
            async with AsyncSession(engine) as session, session.begin():
                scope = await authorize_metric_scope(session, 1, None)
            source = QuerySourceIdentity(
                fixture.tenant,
                publication["id"],
                generation,
                profile["id"],
                profile["version"],
                digest(profile),
                "ISOLATED_TEST",
            )
            count = 0
            for body in supported_queries(profile["id"]):
                units, memberships = expected_streams(fixture, profile, trees, ads, renamed, body)
                manifest = ExpectedUnitManifest(
                    source,
                    1,
                    scope.current.subject_id,
                    scope.auth_version,
                    scope.auth_fingerprint,
                    metric_query_hash(body),
                    body["dataset"],
                    date.fromisoformat(body["date_from"]),
                    date.fromisoformat(body["date_to"]),
                    None,
                    None,
                    None,
                    len(units),
                    stream_hash(units),
                    len(memberships),
                    stream_hash(memberships),
                )
                saved = {
                    "kind": "SQL_ONLY_NOT_PLATFORM",
                    "manifest": encode_manifest(manifest),
                    "units": [item.record() for item in units],
                    "members": [item.record() for item in memberships],
                }
                sql(
                    "INSERT INTO " + expected_registry + " VALUES(%s,1,%s,%s,%s,%s,0)",
                    (
                        fixture.tenant,
                        manifest.query_hash,
                        publication["id"],
                        canonical(saved),
                        digest(saved),
                    ),
                )
                count += 1
            return count
        finally:
            await engine.dispose()

    query_count = asyncio.run(register())
    run_id = str(uuid4())
    control = {
        "version": 1,
        "run_id": run_id,
        "database": database,
        "tenant_id": fixture.tenant,
        "read_registry": read_registry,
        "expected_registry": expected_registry,
    }
    return {
        "kind": "SQL_ONLY_NOT_PLATFORM",
        "control": control,
        "control_path": str(CONTROL_ROOT / run_id / "control.json"),
        "profile": profile,
        "query": query(profile["id"]),
        "registered_query_count": query_count,
        "query_manifest": {
            "datasets": list(DATASETS),
            "page_sizes": [20, 50, 100, 200],
            "granularities": ["SUMMARY", "DAY"],
            "sorts": list(SORTS),
            "directions": ["ASC", "DESC"],
            "ad_summary_spend_desc_q": list(Q_VALUES),
            "scope_snapshot_id": None,
            "channel_id": None,
            "operator_user_id": None,
        },
        "expected": {
            "verified_ad_ids": sorted(ad["entity_id"] for ad in ads),
            "unknown_ad_id": trees[2][3]["entity_id"],
            "summary_ad_count": 22,
            "day_ad_count": 44,
            "literal_name": renamed["name"],
            "literal_entity_id": renamed["entity_id"],
            "queries": list(Q_VALUES),
            "totals": {
                "USD": {"spend": "5040", "ad_count": 21, "registrations": None},
                "EUR": {"spend": "0", "ad_count": 0},
                "GBP": {"spend": None, "ad_count": 0},
            },
            "first_day": "2026-01-01",
            "last_day": "2026-01-02",
            "account_ids": accounts,
            "summary_entity_ids": {
                "ACCOUNT": sorted(tree[0]["entity_id"] for tree in trees),
                "CAMPAIGN": sorted(tree[1]["entity_id"] for tree in (trees[0], trees[2])),
                "ADSET": sorted(tree[2]["entity_id"] for tree in (trees[0], trees[2])),
                "AD": sorted([ad["entity_id"] for ad in ads] + [trees[2][3]["entity_id"]]),
            },
        },
    }
