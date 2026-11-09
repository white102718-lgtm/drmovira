"""056独立真实SQL护栏；只SQL技术夹具，不是Metrics发行或结果Store验收。"""

from itertools import product
from uuid import uuid4

from metric_fact_schema_checks import (
    MetricFactSqlFixture,
    digest,
    validate_metric_fact_schema_target,
)
from metric_profile_query_checks import seed_metric_profile_browser_fixture

METRICS_EXPECTED_MANIFEST_CASES = (
    "pythonMetrics056ExactFourColumnsAndExpectedManifestGuard",
    "pythonMetrics056AllMixedNullRootsAndInvalidHashesCountsReject",
    "pythonMetrics056T1RootsCountsImmutableAcrossBuildGenerationAndLegacyNoRetrofit",
)
FIELDS = (
    "expected_unit_hash",
    "expected_membership_hash",
    "expected_membership_count",
    "expected_manifest_version",
)


def run_metrics_expected_manifest_checks(admin, database, cases):
    validate_metric_fact_schema_target(admin, database)
    fixture = MetricFactSqlFixture(admin, database)
    profile = seed_metric_profile_browser_fixture(admin, database)["profiles"][0]
    publication = fixture.publication(profile, digest(profile), cells=0)
    generation = fixture.publish(publication, facts=0)
    fields = {
        "expected_unit_hash": "a" * 64,
        "expected_membership_hash": "b" * 64,
        "expected_membership_count": 1,
        "expected_manifest_version": "orbit-metric-expectation-canonical-lines-v2",
    }
    metadata = fixture.sql(
        "SELECT COLUMN_NAME,COLUMN_COMMENT FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='orbit_metric_query_snapshot' "
        "AND COLUMN_NAME IN (%s,%s,%s,%s)",
        (database, *FIELDS),
        fetch=True,
    )
    assert len(metadata) == 4 and {row[0] for row in metadata} == set(FIELDS)
    assert all(row[1] for row in metadata)
    triggers = fixture.sql(
        "SELECT TRIGGER_NAME FROM information_schema.TRIGGERS "
        "WHERE TRIGGER_SCHEMA=%s AND TRIGGER_NAME='metric_query_expected_manifest_guard'",
        (database,),
        fetch=True,
    )
    assert triggers == (("metric_query_expected_manifest_guard",),)
    valid = fixture.query(
        publication, generation, expected_account_count=1, expected_cell_count=1, **fields
    )
    cases.append(METRICS_EXPECTED_MANIFEST_CASES[0])

    # 16种NULL组合只允许完整新根和全NULL旧行；其他14种必须真CHECK拒绝。
    for flags in product((False, True), repeat=4):
        changes = {
            field: None if flag else fields[field]
            for field, flag in zip(FIELDS, flags, strict=True)
        }
        row = valid | {"id": str(uuid4())} | changes
        if not any(flags) or all(flags):
            fixture.insert("orbit_metric_query_snapshot", row)
        else:
            fixture.insert("orbit_metric_query_snapshot", row, deny={3819})
    for changes in (
        {"expected_unit_hash": "F" * 64},
        {"expected_membership_hash": "bad"},
        {"expected_membership_count": -1},
        {"expected_membership_count": 9007199254740992},
        {"expected_manifest_version": ""},
        {"expected_account_count": -1},
        {"expected_account_count": 9007199254740992},
        {"expected_cell_count": 9007199254740992},
    ):
        fixture.insert(
            "orbit_metric_query_snapshot", valid | {"id": str(uuid4())} | changes, deny={3819}
        )
    cases.append(METRICS_EXPECTED_MANIFEST_CASES[1])

    for field, value in fields.items():
        replacement = (
            2 if type(value) is int else "changed" if field.endswith("version") else "c" * 64
        )
        fixture.denied(
            f"UPDATE orbit_metric_query_snapshot SET {field}=%s WHERE tenant_id=%s AND id=%s",
            (replacement, fixture.tenant, valid["id"]),
            {1644},
        )
    for field in ("expected_account_count", "expected_cell_count"):
        fixture.denied(
            f"UPDATE orbit_metric_query_snapshot SET {field}={field}+1 "
            "WHERE tenant_id=%s AND id=%s",
            (fixture.tenant, valid["id"]),
            {1644},
        )
    fixture.sql(
        "UPDATE orbit_metric_query_snapshot SET build_generation=build_generation+1 "
        "WHERE tenant_id=%s AND id=%s",
        (fixture.tenant, valid["id"]),
    )
    unchanged = fixture.sql(
        "SELECT expected_unit_hash,expected_membership_hash,"
        "expected_membership_count,expected_manifest_version,"
        "expected_account_count,expected_cell_count "
        "FROM orbit_metric_query_snapshot WHERE tenant_id=%s AND id=%s",
        (fixture.tenant, valid["id"]),
        fetch=True,
    )
    assert unchanged == ((fields[FIELDS[0]], fields[FIELDS[1]], 1, fields[FIELDS[3]], 1, 1),)
    legacy = fixture.query(publication, generation)
    fixture.denied(
        "UPDATE orbit_metric_query_snapshot SET expected_unit_hash=%s,"
        "expected_membership_hash=%s,expected_membership_count=1,expected_manifest_version=%s "
        "WHERE tenant_id=%s AND id=%s",
        (fields[FIELDS[0]], fields[FIELDS[1]], fields[FIELDS[3]], fixture.tenant, legacy["id"]),
        {1644},
    )
    cases.append(METRICS_EXPECTED_MANIFEST_CASES[2])
