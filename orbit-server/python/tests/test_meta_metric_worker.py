"""真实Meta值映射的边界：未知、窗口重叠、数据库精度与稳定维度。"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from orbit_api.errors import OrbitError
from orbit_api.meta_metric_worker import dimension, metric_values

PROFILE = dict(
    register_action_type="register", purchase_action_type="purchase", value_action_type="purchase"
)


def test_missing_insights_and_missing_action_value_remain_unknown():
    assert set(metric_values(None, PROFILE).values()) == {None}
    result = metric_values(
        {
            "spend": "0",
            "actions": [
                {
                    "action_type": "purchase",
                    "value": None,
                    "attribution_values": {"1d_view": "2", "7d_click": "3"},
                }
            ],
        },
        PROFILE,
    )
    assert result["spend"] == "0"
    assert result["purchases"] is None
    assert result["purchase_value"] is None


@pytest.mark.parametrize(
    "value", ["0.0000001", "12345678901234567890123456789", "NaN", "-1", 0.1, True]
)
def test_unrepresentable_values_reject_before_database_rounding(value):
    with pytest.raises(OrbitError):
        metric_values({"spend": value}, PROFILE)


def test_exact_values_normalize_without_rounding_and_duplicate_actions_reject():
    assert metric_values({"spend": "1.2300000"}, PROFILE)["spend"] == "1.23"
    with pytest.raises(OrbitError):
        metric_values({"actions": [{"action_type": "purchase", "value": "1"}] * 2}, PROFILE)


def test_dimensions_preserve_real_parent_and_rename_changes_only_snapshot():
    account, tenant, parent = str(uuid4()), str(uuid4()), str(uuid4())
    row = {"id": "123", "account_id": "42", "name": "原名称"}
    parents = {("ACCOUNT", "42"): parent}
    at = datetime.now(UTC)
    first = dimension(account, tenant, "CAMPAIGN", row, parents, at)
    again = dimension(account, tenant, "CAMPAIGN", row | {"name": "新名称"}, parents, at)
    assert first["entity_id"] == again["entity_id"]
    assert first["id"] != again["id"]
    assert first["parent_snapshot_id"] == parent
    with pytest.raises(OrbitError):
        dimension(account, tenant, "CAMPAIGN", row, {}, at)


@pytest.mark.asyncio
async def test_async_report_resumes_bound_id_without_repeating_creation():
    from dataclasses import asdict
    from datetime import date

    from test_meta_read_adapter import Fake, attribution, config

    from orbit_api.meta_metric_worker import MetaMetricWorker
    from orbit_api.meta_read_adapter import MetaReadAdapter
    from orbit_api.meta_read_contract import InsightWindow

    class Worker(MetaMetricWorker):
        prior = None
        events = []

        async def _checkpoint(self, *args):
            return None

        async def _renew(self, *args):
            return None

        async def _tx(self, actor, job, fence, method, *args):
            self.events.append(method)
            if method == "report_start":
                return self.prior
            if method == "report_bind":
                report = args[0]
                value = asdict(report)
                value["window"] = {
                    "since": report.window.since.isoformat(),
                    "until": report.window.until.isoformat(),
                    "timezone_name": "UTC",
                }
                self.prior = {"state": "BOUND", "report": value}

    fake = Fake(
        {"report_run_id": "456"},
        {
            "id": "456",
            "account_id": "123",
            "async_status": "Job Running",
            "async_percent_completion": 50,
        },
        {
            "id": "456",
            "account_id": "123",
            "async_status": "Job Completed",
            "async_percent_completion": 100,
        },
        {
            "id": "456",
            "account_id": "123",
            "async_status": "Job Completed",
            "async_percent_completion": 100,
        },
        {"data": []},
    )
    worker = Worker(None, None)
    adapter = MetaReadAdapter(config(), transport=fake)
    window = InsightWindow(date(2026, 10, 1), date(2026, 10, 10), "UTC")
    assert not await worker._insights(1, {"id": "job"}, 1, adapter, "123", window, attribution())
    assert worker.events == ["report_start", "report_bind", "report_wait"]
    assert await worker._insights(1, {"id": "job"}, 2, adapter, "123", window, attribution())
    assert sum(call[0] == "POST" for call in fake.calls) == 1
    assert worker.events[-1] == "append_capture"


def test_auth_failure_receipt_cannot_revoke_reauthorized_source():
    from orbit_api.meta_metric_collection import source_revision_matches

    job = dict(tenant_id="tenant", connection_id="connection", connection_revision=2)
    current = dict(tenant_id="tenant", id="connection", revision=2, status="ACTIVE")
    assert source_revision_matches(job, current)
    assert not source_revision_matches(job, current | {"revision": 3})
    assert not source_revision_matches(job, current | {"tenant_id": "other"})
    assert not source_revision_matches(job, current | {"id": "other"})
    assert not source_revision_matches(job, current | {"status": "REAUTH_REQUIRED"})
