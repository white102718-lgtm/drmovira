"""账户18列独立读模型与受控观测发布；事实权限先过滤，缺失不补0。"""

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import bindparam, text

from orbit_api.account_access import clock, context, event, parameters, visible_clause
from orbit_api.account_details_contract import (
    TEXT_FIELDS,
    fact_input,
    fact_interval,
    freeze_attribution,
    invalid,
    iso,
    observed_fields,
    timestamp,
    window,
)
from orbit_api.account_metadata import unknown_observation
from orbit_api.account_selection import selection_sql
from orbit_api.account_store import AccountStore
from orbit_api.configuration_store import MAX_REVISION, _decode
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.identity_contract import _uuid
from orbit_api.reference_access import readable, scope_version
from orbit_api.reference_store import records
from orbit_api.vendor_alias_store import resolve_vendor_alias_snapshots

# 与现有user_store展示合同一致：未知实名回退原昵称/原用户名，不把NULL过滤掉。
PERSON_NAME_SQL = "COALESCE(NULLIF(b.display_name,''),NULLIF(u.nick_name,''),u.user_name)"


def in_query(statement):
    return text(statement).bindparams(bindparam("ids", expanding=True))


def unknown_text():
    return {
        "value": None,
        "code": None,
        "status": "UNSYNCED",
        "reason_code": "NOT_PROVIDED",
        "source": "NOT_PROVIDED",
        "observed_at": None,
    }


def summarize(currency, start, end, aggregate):
    """完整每日覆盖才显示合计或真实0；部分缺失及不可见历史均不泄露部分金额。"""
    expected = (end - start).days + 1 if start is not None and end is not None else 0
    count = aggregate["days"] if aggregate else 0
    complete = expected > 0 and count == expected and aggregate["complete_days"] == expected
    value = unknown_observation(currency, kind="SPEND", source="ACCOUNT_DAY_AGGREGATE")
    if complete:
        total = format(Decimal(aggregate["amount"]), "f")
        if len(total) > 28 and "." in total:
            total = total.rstrip("0").rstrip(".")
        if len(total) > 28:
            raise OrbitError(
                409, "ACCOUNT_AGGREGATE_RANGE_EXCEEDED", "消费合计超过合同金额精度范围"
            )
        value.update(
            amount=total,
            status="SYNCED",
            business_date=start.isoformat() if start == end else None,
            observed_at=iso(aggregate["observed_at"].replace(tzinfo=UTC)),
        )
    return value, "COMPLETE" if complete else "PARTIAL" if count else "NOT_COLLECTED"


class AccountDetailsStore:
    def __init__(self, tokens, *, identity_summary=None):
        self.tokens = tokens
        self.identity_summary = identity_summary

    async def _page(self, session, current, query, after, identifier, limit):
        """预读与clock之后使用同一筛选，避免摘要候选和真实账户页口径分叉。"""
        clauses = ["a.tenant_id=:tenant", "a.id>:after", "(" + visible_clause(current, "a") + ")"]
        params = parameters(current) | {"after": after, "limit": limit}
        if identifier:
            clauses.append("a.id=:id")
            params["id"] = _uuid(identifier, "/id")
        selected_clauses, selected_params = selection_sql(query)
        clauses.extend(selected_clauses)
        params.update(selected_params)
        return list(
            (
                await session.execute(
                    text(
                        "SELECT a.* FROM orbit_ad_account a WHERE "
                        + " AND ".join(clauses)
                        + " ORDER BY a.id LIMIT :limit"
                    ),
                    params,
                )
            ).mappings()
        )

    async def owner_options(self, session, actor, query, page_size=50, cursor=None):
        """只从当前可读账户归属提取投手最小资料，不借用导入或系统人员权限。"""
        current, managed = await context(session, actor, "accounts.read")
        account_version = await clock(session, current)
        scope = await scope_version(session, current)
        fingerprint = hashlib.sha256(
            canonical(
                [
                    actor,
                    current.tenant_id,
                    current.subject_id,
                    current.data_role,
                    current.team_id,
                    managed,
                    scope,
                    account_version,
                    query,
                    page_size,
                ]
            ).encode()
        ).hexdigest()
        after = ""
        if cursor:
            claims = self.tokens.verify("ACCOUNT_DETAILS_OWNER_CURSOR_V1", cursor)
            if claims.get("scope") != fingerprint:
                raise OrbitError(409, "SCOPE_CHANGED", "账户拥有者范围已变化，请重新读取投手")
            after = _uuid(claims.get("after"), "/cursor")
        params = parameters(current) | {
            "after": after,
            "limit": page_size + 1,
            "query": query.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%",
        }
        rows = list(
            (
                await session.execute(
                    text(
                        "SELECT b.id," + PERSON_NAME_SQL + " name,b.team_id,t.name team_name "
                        "FROM orbit_business_user b JOIN sys_user u ON u.user_id=b.user_id "
                        "JOIN orbit_business_team t "
                        "ON t.tenant_id=b.tenant_id AND t.id=b.team_id "
                        "WHERE b.tenant_id=:tenant AND b.id>:after "
                        "AND " + PERSON_NAME_SQL + " LIKE :query ESCAPE '!' "
                        "AND EXISTS(SELECT 1 FROM orbit_ad_account a WHERE a.tenant_id=b.tenant_id "
                        "AND a.owner_user_id=b.id AND (" + visible_clause(current, "a") + ")) "
                        "ORDER BY b.id LIMIT :limit"
                    ),
                    params,
                )
            ).mappings()
        )
        page = rows[:page_size]
        following = (
            self.tokens.issue(
                "ACCOUNT_DETAILS_OWNER_CURSOR_V1",
                {
                    "scope": fingerprint,
                    "after": page[-1]["id"],
                },
            )
            if len(rows) > page_size
            else None
        )
        return {"items": [dict(row) for row in page], "next_cursor": following}

    async def watermark(self, session, tenant, *, write=False):
        if write:
            await session.execute(
                text("INSERT IGNORE INTO orbit_account_details_clock(tenant_id) VALUES(:tenant)"),
                {"tenant": tenant},
            )
        row = (
            (
                await session.execute(
                    text(
                        "SELECT revision,snapshot_id FROM orbit_account_details_"
                        "clock WHERE tenant_id=:tenant " + ("FOR UPDATE" if write else "FOR SHARE")
                    ),
                    {"tenant": tenant},
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row else {"revision": 0, "snapshot_id": None}

    async def list(
        self,
        session,
        actor,
        query,
        cursor=None,
        *,
        identifier=None,
        purpose="ACCOUNT_DETAILS_CURSOR_V1",
    ):
        list_authorization = None
        if self.identity_summary is None:
            current, managed = await context(session, actor, "accounts.read")
        else:
            current, managed, list_authorization = await self.identity_summary.authorize_list(
                session, actor
            )
        summary_ticket = None
        if self.identity_summary is not None:
            # 这里只信任游标MAC及after格式，真正scope/clock一致性仍在下方逐项验证。
            # 独占RC会话的预读只决定可预锁来源；并发新页/新head不得晚补来源锁。
            probe_after = ""
            if cursor:
                probe_after = _uuid(self.tokens.verify(purpose, cursor).get("after"), "/cursor")
            candidates = await self._page(
                session, current, query, probe_after, identifier, query["page_size"]
            )
            summary_ticket = await self.identity_summary.prepare_for_list(
                session, actor, [row["id"] for row in candidates], list_authorization
            )
        account_version = await clock(session, current)
        scope = await scope_version(session, current)
        catalog_version = (
            await session.execute(
                text(
                    "SELECT revision FROM orbit_reference_clock WHERE tenant_id=:tenant FOR SHARE"
                ),
                {"tenant": current.tenant_id},
            )
        ).scalar_one()
        watermark = await self.watermark(session, current.tenant_id)
        fingerprint = hashlib.sha256(
            canonical(
                [
                    actor,
                    current.tenant_id,
                    current.subject_id,
                    current.data_role,
                    current.team_id,
                    managed,
                    scope,
                    catalog_version,
                    query,
                    identifier,
                ]
            ).encode()
        ).hexdigest()
        after = ""
        now = (
            (await session.execute(text("SELECT UTC_TIMESTAMP(3)")))
            .scalar_one()
            .replace(tzinfo=UTC)
        )
        if cursor:
            claims = self.tokens.verify(purpose, cursor)
            if (
                claims.get("scope") != fingerprint
                or claims.get("account") != account_version
                or claims.get("details") != watermark["revision"]
            ):
                raise OrbitError(409, "SCOPE_CHANGED", "账户、观测或授权已变化，请重新查询")
            after = _uuid(claims.get("after"), "/cursor")
            try:
                now = datetime.fromisoformat(
                    timestamp(claims.get("reference"), "/cursor").replace("Z", "+00:00")
                )
            except OrbitError:
                raise OrbitError(400, "TOKEN_INVALID", "账户日期游标无效") from None
        rows = await self._page(session, current, query, after, identifier, query["page_size"] + 1)
        if identifier and not rows:
            raise OrbitError(404, "NOT_FOUND", "账户不存在或不可见")
        page = rows[: query["page_size"]]
        items = await self.enrich(
            session, current, managed, page, query, now, watermark["snapshot_id"]
        )
        if summary_ticket is not None:
            summaries = await self.identity_summary.resolve(session, actor, page, summary_ticket)
            for item in items:
                # 缺少完整来源/合法seal保持原未知，不扫描资源、不推断真实0。
                if item["account"]["id"] in summaries:
                    item["details"].update(summaries[item["account"]["id"]])
        following = (
            self.tokens.issue(
                purpose,
                {
                    "scope": fingerprint,
                    "account": account_version,
                    "details": watermark["revision"],
                    "after": page[-1]["id"],
                    "reference": iso(now),
                },
            )
            if len(rows) > len(page)
            else None
        )
        return {
            "items": items,
            "next_cursor": following,
            "data_as_of": iso(now),
            "scope_version": scope,
            "account_version": account_version,
            "metric_snapshot_id": watermark["snapshot_id"],
        }

    async def enrich(self, session, current, managed, page, query, now, snapshot):
        if not page:
            return []
        params = parameters(current) | {"ids": [row["id"] for row in page]}
        observations = {
            row["account_id"]: row
            for row in (
                await session.execute(
                    in_query(
                        "SELECT account_id,revision,value_json FROM orbit_account_details_current "
                        "WHERE tenant_id=:tenant AND account_id IN :ids"
                    ),
                    params,
                )
            ).mappings()
        }
        vendors = await records(
            session, current.tenant_id, list({r["vendor_id"] for r in page if r["vendor_id"]})
        )
        # 无引用目录对象时结果必为空，不进入户商来源的重复授权/管理团队查询。
        # 有户商时仍逐次走原helper权限与来源校验，不缓存或回退代称。
        aliases = (
            await resolve_vendor_alias_snapshots(session, current, list(vendors)) if vendors else {}
        )
        owner_ids = list({r["owner_user_id"] for r in page})
        owners = {
            r["id"]: r["display_name"]
            for r in (
                await session.execute(
                    in_query(
                        "SELECT b.id," + PERSON_NAME_SQL + " display_name "
                        "FROM orbit_business_user b JOIN sys_user u ON u.user_id=b.user_id "
                        "WHERE b.tenant_id=:tenant AND b.id IN :ids"
                    ),
                    params | {"ids": owner_ids},
                )
            ).mappings()
        }
        # 当前账户范围之外，历史事实还必须与冻结投手/团队范围求交集。
        fact_scope = "(" + visible_clause(current, "f") + ")"
        if current.data_role == "TEAM_ADMIN":
            fact_scope = "(" + fact_scope + " OR f.owner_user_id IS NULL)"
        earliest = {}
        if query["mode"] == "MAX":
            earliest = {
                r["account_id"]: r["first_day"]
                for r in (
                    await session.execute(
                        in_query(
                            "SELECT f.account_id,MIN(f.business_date) first_day FROM"
                            " orbit_account_spend_day f "
                            "WHERE f.tenant_id=:tenant AND f.account_id IN :ids AND "
                            + fact_scope
                            + " GROUP BY f.account_id"
                        ),
                        params,
                    )
                ).mappings()
            }
        windows = {
            r["id"]: window(query, r["timezone_id"], now, earliest.get(r["id"])) for r in page
        }
        ranges = [
            {"id": key, "start": start.isoformat(), "end": end.isoformat()}
            for key, (start, end) in windows.items()
            if start and end
        ]
        aggregates = {}
        if ranges:
            aggregates = {
                r["account_id"]: r
                for r in (
                    await session.execute(
                        text(
                            "SELECT f.account_id,COUNT(*) days,SUM(f.coverage='COMPL"
                            "ETE' AND f.amount IS NOT NULL) complete_days,"
                            "SUM(f.amount) amount,MAX(f.observed_at) observed_at FROM "
                            "JSON_TABLE(:ranges,'$[*]' COLUMNS(account_id CHAR(36) PATH '$.id',"
                            "date_from DATE PATH '$.start',date_to DATE PATH '$.end')) w "
                            # 当前页账户先驱动复合主键，避免优化器反转后每页扫描租户全部事实。
                            "STRAIGHT_JOIN orbit_account_spend_day f FORCE INDEX (PRIMARY) "
                            "ON f.tenant_id=:tenant A"
                            "ND f.account_id=w.account_id COLLATE utf8mb4_0900_as_cs "
                            "AND f.business_date BETWEEN w.date_from AND w.date_to WHERE "
                            + fact_scope
                            + " GROUP BY f.account_id"
                        ),
                        parameters(current) | {"ranges": canonical(ranges)},
                    )
                ).mappings()
            }
        result = []
        for row in page:
            core = AccountStore.public(row, now)
            vendor = vendors.get(row["vendor_id"])
            vendor_value = _decode(vendor["value_json"]) if vendor else None
            vendor_display = (
                vendor_value.get("name")
                if vendor
                and vendor["kind"] == "VENDOR"
                and readable(current, managed, vendor_value)
                else None
            )
            # 实时真实alias独立于完整资料name，未知不回退；历史由020事务快照保留。
            alias = aliases.get(row["vendor_id"])
            core["vendor_alias"] = alias["alias"] if alias else None
            record = observations.get(row["id"])
            saved = _decode(record["value_json"]) if record else {}
            if "balance" in saved:
                core["balance"] = saved["balance"]
            start, end = windows[row["id"]]
            core["spend"], coverage = summarize(
                row["currency"], start, end, aggregates.get(row["id"])
            )
            details = {key: saved.get(key, unknown_text()) for key in TEXT_FIELDS}
            details.update(
                {
                    "account_id": row["id"],
                    "revision": row["revision"],
                    "source_revision": record["revision"] if record else 0,
                    "owner_display": owners.get(row["owner_user_id"]),
                    "vendor_display": {
                        "name": vendor_display,
                        "source": "REFERENCE_CATALOG",
                        "reason_code": None
                        if core["vendor_alias"] is not None
                        else "ALIAS_UNSET"
                        if alias
                        else "NOT_PROVIDED",
                        "alias_source": alias["source"] if alias else "NOT_VISIBLE",
                        "alias_revision": alias["alias_revision"] if alias else None,
                    },
                    "payable": saved.get(
                        "payable", unknown_observation(row["currency"], kind="BILL")
                    ),
                    "lifetime_spend": saved.get(
                        "lifetime_spend", unknown_observation(row["currency"], kind="SPEND")
                    ),
                    "business_managers": None,
                    "identity_status": "UNSYNCED",
                    "identity_observed_at": None,
                    "identity_count": None,
                    "authorized_at": None,
                    "unbound_at": iso(row["unbound_at"].replace(tzinfo=UTC))
                    if row["unbound_at"]
                    else None,
                    "blocked_observed_at": details["blocked_reason"]["observed_at"],
                    "note": None,
                    "spend_window": {
                        "mode": query["mode"],
                        "date_from": start.isoformat() if start else None,
                        "date_to": end.isoformat() if end else None,
                        "timezone": row["timezone_id"],
                        "reference_at": iso(now),
                        "coverage": coverage,
                        "snapshot_id": snapshot,
                    },
                }
            )
            result.append({"account": core, "details": details})
        return result

    async def publish(self, session, actor, expected_revision, *, facts=(), observations=()):
        """内部受控采集入口；调用者须在外层事务内调用，不向浏览器开放伪造观测写入。"""
        if (
            type(expected_revision) is not int
            or not 0 <= expected_revision < MAX_REVISION
            or not isinstance(facts, (list, tuple))
            or not isinstance(observations, (list, tuple))
            or not 1 <= len(facts) + len(observations) <= 1000
        ):
            invalid("/publication")
        if any(not isinstance(r, dict) for r in [*facts, *observations]):
            invalid("/publication")
        facts = [r | {"account_id": _uuid(r.get("account_id"), "/account_id")} for r in facts]
        observations = [
            r | {"account_id": _uuid(r.get("account_id"), "/account_id")} for r in observations
        ]
        if not session.in_transaction():
            raise ValueError("观测发布必须由调用方显式事务包裹")
        current, _ = await context(session, actor, "accounts.sync")
        await clock(session, current, write=True)
        watermark = await self.watermark(session, current.tenant_id, write=True)
        if watermark["revision"] != expected_revision:
            raise OrbitError(409, "REVISION_CONFLICT", "账户观测发布水位已变化")
        ids = sorted(
            {
                _uuid(r.get("account_id"), "/account_id")
                for r in [*facts, *observations]
                if isinstance(r, dict)
            }
        )
        if not ids or any(not isinstance(r, dict) for r in [*facts, *observations]):
            invalid("/publication")
        params = parameters(current) | {"ids": ids}
        accounts = {
            r["id"]: r
            for r in (
                await session.execute(
                    in_query(
                        "SELECT a.* FROM orbit_ad_account a WHERE a.tenant_id=:t"
                        "enant AND a.id IN :ids AND ("
                        + visible_clause(current, "a")
                        + ") ORDER BY a.id FOR UPDATE"
                    ),
                    params,
                )
            ).mappings()
        }
        if len(accounts) != len(ids):
            raise OrbitError(404, "NOT_FOUND", "发布账户不存在或不可见")
        prepared, seen, keys = [], set(), []
        for raw in facts:
            row = accounts[raw["account_id"]]
            item = fact_input(raw, row["currency"], row["timezone_id"])
            key = (item["account_id"], item["business_date"])
            if key in seen:
                invalid("/facts", "同次发布不可重复账户业务日")
            seen.add(key)
            start, end = fact_interval(
                item["business_date"], row["timezone_id"], item["observed_at"]
            )
            keys.append(
                {
                    "id": item["account_id"],
                    "day": item["business_date"].isoformat(),
                    "start": start.isoformat(sep=" "),
                    "end": end.isoformat(sep=" "),
                }
            )
            prepared.append(item)
        extra, seen = [], set()
        for item in observations:
            if set(item) != {"account_id", "observations"} or item["account_id"] in seen:
                invalid("/observations")
            seen.add(item["account_id"])
            extra.append(
                (
                    item["account_id"],
                    observed_fields(item["observations"], accounts[item["account_id"]]["currency"]),
                )
            )
        snapshot = str(uuid4())
        common = {"tenant": current.tenant_id, "snapshot": snapshot}
        # 只关联输入的至多1000个业务日，不加载账户全部历史；发布器共用租户账户锁。
        json_keys = (
            "JSON_TABLE(:keys,'$[*]' COLUMNS(account_id CHAR(36) PATH '$.id',"
            "business_date DATE PATH '$.day',window_start DATETIME(3) PATH '$.start',"
            "window_end DATETIME(3) PATH '$.end')) w "
        )
        owners, prior_facts = {}, {}
        if keys:
            matched = (
                await session.execute(
                    text(
                        "SELECT w.account_id,w.business_date,h.owner_user_id,h.owner_team_id,"
                        "h.starts_at,h.ends_at FROM "
                        + json_keys
                        + "JOIN orbit_account_assignment h ON h.tenant_id=:tenant "
                        "AND h.account_id=w.account_id COLLATE utf8mb4_0900_as_cs "
                        "AND h.starts_at<w.window_end "
                        "AND (h.ends_at IS NULL OR h.ends_at>w.window_start) "
                        # JSON_TABLE为虚表，仅锁定实际归属表，避免虚表重复锁错误3569。
                        "ORDER BY w.account_id,w.business_date,h.starts_at "
                        "LIMIT 2001 FOR SHARE OF h"
                    ),
                    common | {"keys": canonical(keys)},
                )
            ).mappings()
            matched = list(matched)
            if len(matched) >= 2001:
                raise OrbitError(409, "ATTRIBUTION_HISTORY_LIMIT", "归属历史异常过多，须先核验区间")
            for item in matched:
                key = (item["account_id"], item["business_date"])
                owners.setdefault(key, []).append(item)
            prior_facts = {
                (r["account_id"], r["business_date"]): r
                for r in (
                    await session.execute(
                        text(
                            "SELECT f.account_id,f.business_date,f.revision,f.observed_at,"
                            "f.owner_user_id,f.owner_team_id,f.attribution_version,"
                            "f.attribution_reason FROM "
                            + json_keys
                            + "JOIN orbit_account_spend_day f ON f.tenant_id=:tenant "
                            "AND f.account_id=w.account_id COLLATE utf8mb4_0900_as_cs "
                            "AND f.business_date=w.business_date FOR UPDATE OF f"
                        ),
                        common | {"keys": canonical(keys)},
                    )
                ).mappings()
            }
        fact_values = []
        for fact in prepared:
            key = (fact["account_id"], fact["business_date"])
            previous = prior_facts.get(key)
            start, end = fact_interval(
                fact["business_date"],
                accounts[fact["account_id"]]["timezone_id"],
                fact["observed_at"],
            )
            attribution = freeze_attribution(start, end, owners.get(key, []), previous)
            if previous and fact["observed_at"] <= previous["observed_at"]:
                raise OrbitError(409, "OBSERVATION_STALE", "迟到或重复消费观测不能覆盖新版本")
            version = previous["revision"] + 1 if previous else 1
            if version > MAX_REVISION:
                raise OrbitError(409, "REVISION_EXHAUSTED", "消费观测版本已达上限")
            fact_values.append(
                common
                | fact
                | {
                    "revision": version,
                    **attribution,
                }
            )
        prior_extra = (
            {
                r["account_id"]: r
                for r in (
                    await session.execute(
                        in_query(
                            "SELECT account_id,revision,value_json "
                            "FROM orbit_account_details_current "
                            "WHERE tenant_id=:tenant AND account_id IN :ids FOR UPDATE"
                        ),
                        common | {"ids": [item[0] for item in extra]},
                    )
                ).mappings()
            }
            if extra
            else {}
        )
        detail_values = []
        for identifier, value in extra:
            prior = prior_extra.get(identifier)
            old = _decode(prior["value_json"]) if prior else {}
            for key, observation in value.items():
                if old.get(key, {}).get("observed_at") and (
                    not observation["observed_at"]
                    or observation["observed_at"] <= old[key]["observed_at"]
                ):
                    raise OrbitError(409, "OBSERVATION_STALE", "迟到字段观测不能覆盖新版本")
            version = prior["revision"] + 1 if prior else 1
            if version > MAX_REVISION:
                raise OrbitError(409, "REVISION_EXHAUSTED", "附加观测版本已达上限")
            detail_values.append(
                common | {"id": identifier, "value": canonical(old | value), "revision": version}
            )
        # 校验全量通过后executemany；历史/当前/水位/审计同一事务，失败不留下部分发布。
        if fact_values:
            columns = (
                "tenant_id,account_id,business_date,currency,amount,coverage,"
                "owner_user_id,owner_team_id,source,observed_at,revision,snapshot_id,"
                "attribution_version,attribution_reason"
            )
            values = (
                ":tenant,:account_id,:business_date,:currency,:amount,:coverage,"
                ":owner_user_id,:owner_team_id,:source,:observed_at,:revision,:snapshot,"
                ":attribution_version,:attribution_reason"
            )
            await session.execute(
                text(
                    "INSERT INTO orbit_account_spend_day_history ("
                    + columns
                    + ") VALUES("
                    + values
                    + ")"
                ),
                fact_values,
            )
            await session.execute(
                text(
                    "INSERT INTO orbit_account_spend_day ("
                    + columns
                    + ") VALUES("
                    + values
                    + ") ON DUPLICATE KEY UPDATE amount=VALUES(amount),"
                    "coverage=VALUES(coverage),owner_user_id=VALUES(owner_user_id),"
                    "owner_team_id=VALUES(owner_team_id),source=VALUES(source),"
                    "observed_at=VALUES(observed_at),revision=VALUES(revision),snapshot_id=VALUES(snapshot_id)"
                ),
                fact_values,
            )
        if detail_values:
            columns = "tenant_id,account_id,revision,value_json,snapshot_id,"
            values = "VALUES(:tenant,:id,:revision,:value,:snapshot,UTC_TIMESTAMP(3))"
            await session.execute(
                text(
                    "INSERT INTO orbit_account_details_history ("
                    + columns
                    + "received_at) "
                    + values
                ),
                detail_values,
            )
            await session.execute(
                text(
                    "INSERT INTO orbit_account_details_current ("
                    + columns
                    + "updated_at) "
                    + values
                    + " ON DUPLICATE KEY UPDATE revision=VALUES(revision),"
                    "value_json=VALUES(value_json),snapshot_id=VALUES(snapshot_id),updated_at=VALUES(updated_at)"
                ),
                detail_values,
            )
        await session.execute(
            text(
                "UPDATE orbit_account_details_clock SET revision=revision+1,"
                "snapshot_id=:snapshot WHERE tenant_id=:tenant"
            ),
            common,
        )
        await event(
            session,
            current,
            "OBSERVATION",
            snapshot,
            1,
            "ACCOUNT_OBSERVATIONS_PUBLISHED",
            snapshot,
            {"facts": len(prepared), "accounts": len(extra), "watermark": expected_revision + 1},
        )
        return {"revision": expected_revision + 1, "snapshot_id": snapshot}
