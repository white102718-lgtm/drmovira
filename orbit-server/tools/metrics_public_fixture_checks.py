"""真实公开Metrics成功链；来源是独立SQL登记，不冒称生产平台发行。"""

import json
from decimal import Decimal
from uuid import uuid4

from metrics_browser_fixture import control_path, prepare_metrics_browser_fixture, validate_control
from metrics_query_read_checks import guard_target

from orbit_api.metrics_contract import parse_metrics

METRICS_PUBLIC_FIXTURE_CASES = [
    "pythonMetricsPublicIndependentRegisteredSourceAndExpectedManifest",
    "pythonMetricsPublicFourDatasetsExactPagesAndWholeCurrencyTotals",
    "pythonMetricsPublicDayRowsAndNullableUnknownRemainExact",
    "pythonMetricsPublicLiteralSearchAndIdempotentIntentBoundary",
]


def publish_control(fixture, destination):
    """控制文件只有白名单定位；不携带凭据、SQL、用户或查询结果。"""
    path = control_path(destination)
    control = dict(fixture["control"], run_id=path.parent.name)
    validate_control(control, path)
    path.parent.mkdir(parents=True, exist_ok=False)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(control, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
    return path


def run_metrics_public_fixture_checks(
    client, admin, headers, password, cache, database, cases, *, destination
):
    guard_target(admin, database)
    fixture = prepare_metrics_browser_fixture(client, admin, headers, password, cache, database)
    assert fixture["registered_query_count"] == 460
    publish_control(fixture, destination)
    context = client.get("/api/v1/metrics/capabilities", headers=headers)
    assert context.status_code == 200 and set(context.json()) == {"csrf_token"}
    csrf = context.json()["csrf_token"]
    cases.append(METRICS_PUBLIC_FIXTURE_CASES[0])

    def post(body, key=None):
        response = client.post(
            "/api/v1/metrics/query",
            headers=headers | {"X-CSRF-Token": csrf, "Idempotency-Key": key or uuid4().hex},
            json=body,
        )
        assert response.status_code == 200, (
            "metrics_public_fixture_status",
            response.status_code,
            response.json().get("code"),
        )
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-request-id"]
        parsed = parse_metrics(response.content)
        assert parsed == response.json()
        return parsed

    expected = fixture["expected"]

    def totals(value, *, usd_spend="5040", usd_ads=21):
        result = {item["currency"]: item for item in value["totals"]}
        assert set(result) == {"USD", "EUR", "GBP"}
        for currency, original_proof in expected["totals"].items():
            proof = dict(original_proof)
            if currency == "USD":
                proof.update(spend=usd_spend, ad_count=usd_ads)
            actual = result[currency]
            spend = actual["values"]["spend"]
            assert (spend is None and proof["spend"] is None) or (
                spend is not None
                and proof["spend"] is not None
                and Decimal(spend) == Decimal(proof["spend"])
            )
            assert actual["ad_count"] == proof["ad_count"]
        assert result["USD"]["values"]["registrations"] is None
        assert result["USD"]["coverage"] == "1" and result["USD"]["missing_count"] == 0
        assert value["missing_count"] == 2
        assert result["EUR"]["coverage"] == "1" and result["GBP"]["coverage"] == "0"

    def all_pages(body):
        first = post(body)
        items, cursor, seen = list(first["items"]), first["next_cursor"], set()
        totals(first)
        while cursor:
            assert cursor not in seen
            seen.add(cursor)
            page = post(body | {"cursor": cursor})
            assert page["query_snapshot_id"] == first["query_snapshot_id"]
            assert page["totals"] == first["totals"]
            items.extend(page["items"])
            cursor = page["next_cursor"]
        keys = [(row["entity_id"], row["currency"], row["business_date"]) for row in items]
        assert len(set(keys)) == len(keys)
        return items

    for dataset, ids in expected["summary_entity_ids"].items():
        for size in (20, 50, 100, 200):
            body = fixture["query"] | {"dataset": dataset, "page_size": size}
            items = all_pages(body)
            assert sorted(row["entity_id"] for row in items) == ids
    cases.append(METRICS_PUBLIC_FIXTURE_CASES[1])

    for size in (20, 50, 100, 200):
        items = all_pages(fixture["query"] | {"granularity": "DAY", "page_size": size})
        assert len(items) == expected["day_ad_count"]
        assert {(row["entity_id"], row["business_date"]) for row in items} == {
            (entity, day)
            for entity in expected["summary_entity_ids"]["AD"]
            for day in (expected["first_day"], expected["last_day"])
        }
        unknown = [row for row in items if row["entity_id"] == expected["unknown_ad_id"]]
        assert len(unknown) == 2
        assert all(
            row["quality"] == "UNKNOWN" and row["values"]["spend"] is None for row in unknown
        )
    cases.append(METRICS_PUBLIC_FIXTURE_CASES[2])

    original = fixture["query"]
    key = uuid4().hex
    first = post(original, key)
    assert post(original, key) == first
    conflict = client.post(
        "/api/v1/metrics/query",
        headers=headers | {"X-CSRF-Token": csrf, "Idempotency-Key": key},
        json=original | {"q": "%_!"},
    )
    assert conflict.status_code == 409
    for q in ("中文", "%_!", "不存在的指标"):
        value = post(original | {"q": q})
        print(
            json.dumps(
                {
                    "metric_query_literal_diagnostic": q,
                    "totals": [
                        {
                            "currency": t["currency"],
                            "spend": t["values"]["spend"],
                            "ad_count": t["ad_count"],
                            "coverage": t["coverage"],
                            "missing_count": t["missing_count"],
                        }
                        for t in value["totals"]
                    ],
                },
                ensure_ascii=True,
            ),
            flush=True,
        )
        # 汇总覆盖当前筛选的完整结果，不能把筛选前的5040冒充筛选后的汇总。
        totals(
            value,
            usd_spend="0" if q == "不存在的指标" else "240" if q == "%_!" else "5040",
            usd_ads=0 if q == "不存在的指标" else 1 if q == "%_!" else 21,
        )
        if q == "不存在的指标":
            assert value["items"] == [] and value["next_cursor"] is None
        elif q == "%_!":
            assert len(value["items"]) == 1
            row = value["items"][0]
            assert row["entity_id"] == expected["literal_entity_id"]
            assert row["name"] == expected["literal_name"]
            assert Decimal(row["values"]["spend"]) == Decimal("240")
        else:
            assert sorted(row["entity_id"] for row in all_pages(original | {"q": q})) == sorted(
                expected["verified_ad_ids"]
            )
    cases.append(METRICS_PUBLIC_FIXTURE_CASES[3])
    return {
        "version": 1,
        "kind": fixture["kind"],
        "route": "/orbit/monitor/data",
        "profile": {key: fixture["profile"][key] for key in ("id", "version")},
        "query": original,
        "expected": expected,
    }
