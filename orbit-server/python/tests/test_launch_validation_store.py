"""Store协议纯测试：替身仅验证事务/授权调用边界，不能代替MySQL验收。"""

import copy
from contextlib import AbstractAsyncContextManager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_launch_validation_contract import fixture, uid

from orbit_api.authorization import BusinessContext
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_plan_source import PlanSource
from orbit_api.launch_validation_store import (
    FREEZE_FIELDS,
    LaunchValidationStore,
    ObservationReference,
    ValidationAuthorityProvider,
    ValidationEvidence,
    ValidationIssue,
    _checked_evidence,
)


class Transaction(AbstractAsyncContextManager):
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        self.session.transaction = True

    async def __aexit__(self, *args):
        self.session.transaction = False


class Session(AbstractAsyncContextManager):
    def __init__(self, env, *, host="127.0.0.1", port=13306, database=None):
        self.env, self.transaction = env, False
        self.bind = SimpleNamespace(url=SimpleNamespace(host=host, port=port))
        self.database = database or "orbit_py_it_" + "a" * 32

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.transaction = False

    def begin(self):
        return Transaction(self)

    def in_transaction(self):
        return self.transaction

    async def execute(self, statement, params=None):
        sql, params = str(statement), params or {}
        self.env.calls.append((sql, params))
        if sql == "SELECT DATABASE()":
            return SimpleNamespace(scalar_one=lambda: self.database)
        if sql == "SELECT UTC_TIMESTAMP(3)":
            return SimpleNamespace(scalar_one=lambda: self.env.now)
        if sql.startswith("SELECT 1 FROM orbit_launch_idempotency"):
            return SimpleNamespace(first=lambda: (1,) if self.env.saved else None)
        if "FROM orbit_launch_allocation " in sql:
            return SimpleNamespace(
                mappings=lambda: SimpleNamespace(first=lambda: self.env.allocation_row)
            )
        if "FROM orbit_launch_name_reservation " in sql:
            return SimpleNamespace(
                mappings=lambda: SimpleNamespace(first=lambda: self.env.name_row)
            )
        if "FROM orbit_launch_allocation_item " in sql:
            return SimpleNamespace(
                mappings=lambda: SimpleNamespace(all=lambda: self.env.allocation_items)
            )
        if "FROM orbit_launch_name_item " in sql:
            return SimpleNamespace(
                mappings=lambda: SimpleNamespace(all=lambda: self.env.name_items)
            )
        if sql.startswith("UPDATE orbit_launch_plan SET"):
            self.env.head["revision"], self.env.head["state"] = params["revision"], params["state"]
            return SimpleNamespace(rowcount=self.env.update_count)
        if sql.lstrip().startswith("INSERT INTO orbit_launch_validation"):
            if self.env.fail_persist:
                raise RuntimeError("受控持久化失败，不代表真实MySQL回滚测试")
            self.env.persisted.append(params)
            return SimpleNamespace(rowcount=1)
        raise AssertionError("纯工具未声明SQL")


class Provider(ValidationAuthorityProvider):
    def __init__(self, env):
        self.env = env

    async def capture(self, value):
        assert not self.env.pre_session.in_transaction()
        self.env.order.append("capture-outside")
        self.env.input = value
        return self.env.evidence

    async def revalidate(self, session, current, source, evidence):
        assert session.in_transaction()
        self.env.order.append("source-locks")
        return self.env.fresh or evidence


class Environment:
    def __init__(self, monkeypatch):
        plan, args = fixture()
        self.plan, self.args = plan, args
        self.current = BusinessContext(1, uid(900), "USER", uid(90), uid(91))
        self.head = {
            "id": args["plan_id"],
            "revision": 7,
            "state": "DRAFT",
            "payload_json": plan,
            "payload_hash": "b" * 64,
            **plan["ownership"],
        }
        self.source = PlanSource(
            self.current.tenant_id, args["plan_id"], 7, 7, "b" * 64, canonical(plan).encode()
        )
        self.evidence = ValidationEvidence(
            "c" * 64,
            9,
            40,
            (),
            (ObservationReference("ACCOUNT", uid(100), 2),),
            canonical({key: args[key] for key in FREEZE_FIELDS}).encode(),
        )
        self.allocation_row = {
            key: args["allocation"][key]
            for key in ("plan_id", "plan_revision", "state", "algorithm_version", "input_hash")
        }
        self.allocation_row["active"] = 1
        self.name_row = {
            "plan_id": args["plan_id"],
            "plan_revision": 7,
            "naming_date": "2026-11-08",
        }
        self.allocation_items = copy.deepcopy(args["allocation"]["items"])
        self.name_items = copy.deepcopy(args["name_reservation"]["items"])
        self.now = datetime(2026, 11, 8, 8, tzinfo=UTC)
        self.calls, self.order, self.persisted, self.events = [], [], [], []
        self.saved, self.fresh, self.input = None, None, None
        self.update_count, self.fail_persist = 1, False
        self.pre_session = Session(self)
        self.final_session = Session(self)
        self.final_session.transaction = True
        self.provider = Provider(self)
        self.store = LaunchValidationStore(object(), self.provider)
        self.value = {
            "allocation_id": args["allocation"]["id"],
            "name_reservation_id": args["name_reservation"]["id"],
        }

        async def context(*args):
            assert args[2] == "launch.edit"
            self.order.append("authorize")
            return self.current

        async def clock(*args, **kwargs):
            self.order.append("launch-clock")

        async def row(*args, **kwargs):
            self.order.append("head" if not kwargs.get("unlocked") else "scope")
            return copy.deepcopy(self.head)

        async def source(*args):
            self.order.append("source-version")
            return self.source

        async def replay(*args):
            return self.saved

        async def event(*args):
            self.events.append(args)

        async def remember(*args):
            self.saved = args[-1]

        monkeypatch.setattr("orbit_api.launch_validation_store.access.context", context)
        monkeypatch.setattr("orbit_api.launch_validation_store.access.clock", clock)
        monkeypatch.setattr("orbit_api.launch_validation_store.LaunchStore.row", row)
        monkeypatch.setattr("orbit_api.launch_validation_store.capture_plan_source", source)
        monkeypatch.setattr("orbit_api.launch_validation_store.access.replay", replay)
        monkeypatch.setattr("orbit_api.launch_validation_store.access.event", event)
        monkeypatch.setattr("orbit_api.launch_validation_store.access.remember", remember)
        monkeypatch.setattr("orbit_api.launch_validation_store.verify_csrf", lambda *args: None)

    async def prepare(self):
        return await self.store.prepare(
            lambda: self.pre_session,
            1,
            "会话占位仅纯测",
            "csrf纯测",
            "idempotency-fixture",
            self.value,
            self.args["plan_id"],
            7,
        )

    async def validate(self, prepared):
        return await self.store.validate(
            self.final_session,
            1,
            "会话占位仅纯测",
            "csrf纯测",
            "idempotency-fixture",
            self.value,
            self.args["plan_id"],
            7,
            uid(999),
            prepared,
        )


@pytest.mark.asyncio
async def test_network_capture_outside_transaction_and_final_lock_order_and_atomic_calls(
    monkeypatch,
):
    env = Environment(monkeypatch)
    prepared = await env.prepare()
    assert env.order[-1] == "capture-outside"
    env.order.clear()
    # 完整树只能在无事务阶段算一次；final不重新调用freeze。
    monkeypatch.setattr(
        "orbit_api.launch_validation_store.freeze_validation",
        lambda *a, **k: pytest.fail("final重新展开树"),
    )
    env.now += timedelta(seconds=12)
    result = await env.validate(prepared)
    assert (
        env.order.index("source-locks")
        < env.order.index("launch-clock")
        < env.order.index("head")
        < env.order.index("source-version")
    )
    assert result["valid"] and env.head["state"] == "VALIDATED" and env.head["revision"] == 8
    assert env.persisted[0]["source"] == 7 and env.persisted[0]["head"] == 8
    assert env.persisted[0]["validated"] == env.now.replace(tzinfo=None)
    assert env.persisted[0]["expires"] - env.persisted[0]["validated"] == timedelta(minutes=15)
    assert len(env.events) == 1 and env.saved == result
    assert not any("INSERT INTO orbit_launch_plan_version" in sql for sql, _ in env.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("state,revision", [("DRAFT", 7), ("VALIDATED", 8)])
async def test_business_invalid_returns_real_counts_and_invalidates_old_success(
    monkeypatch, state, revision
):
    env = Environment(monkeypatch)
    env.head["state"] = state
    env.evidence = replace(
        env.evidence,
        errors=(ValidationIssue("/campaigns/0", "CAPABILITY_UNVERIFIED", "能力尚未核验"),),
        freeze_arguments_json=None,
    )
    result = await env.validate(await env.prepare())
    assert result["valid"] is False and result["hash"] is None and result["expires_at"] is None
    assert result["ad_count"] == 4 and result["budget_totals"] == [
        {"currency": "USD", "amount": "24.68"}
    ]
    assert env.head["state"] == "DRAFT" and env.head["revision"] == revision
    assert not env.persisted and len(env.events) == 1 and env.saved == result


@pytest.mark.asyncio
async def test_success_replay_current_authorization_before_old_cas_and_provider_independent(
    monkeypatch,
):
    env = Environment(monkeypatch)
    original = await env.validate(await env.prepare())
    env.store.provider = None
    env.order.clear()
    prepared = await env.prepare()
    assert prepared.evidence is None
    assert await env.validate(prepared) == original
    assert env.order[0] == "authorize" and "capture-outside" not in env.order
    assert len(env.persisted) == 1


@pytest.mark.asyncio
async def test_replay_cannot_skip_revoked_action_or_hidden_plan(monkeypatch):
    env = Environment(monkeypatch)
    await env.validate(await env.prepare())
    revoked = AsyncMock(side_effect=OrbitError(403, "PERMISSION_DENIED", "已撤权"))
    monkeypatch.setattr("orbit_api.launch_validation_store.access.context", revoked)
    with pytest.raises(OrbitError) as info:
        await env.prepare()
    assert info.value.status == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "damage",
    [
        "head",
        "source",
        "fingerprint",
        "actor",
        "allocation_owner",
        "allocation_source",
        "allocation_state",
        "name_source",
    ],
)
async def test_final_drift_no_write(monkeypatch, damage):
    env = Environment(monkeypatch)
    prepared = await env.prepare()
    if damage == "head":
        env.head["revision"] += 1
    elif damage == "source":
        env.source = replace(env.source, payload_hash="d" * 64)
    elif damage == "fingerprint":
        env.fresh = replace(env.evidence, fingerprint="d" * 64)
    elif damage == "actor":
        env.current = replace(env.current, subject_id=uid(999))
    elif damage == "allocation_owner":
        env.allocation_row["plan_id"] = uid(999)
    elif damage == "allocation_source":
        env.allocation_row["plan_revision"] += 1
    elif damage == "allocation_state":
        env.allocation_row["state"] = "FAILED"
    else:
        env.name_row["plan_revision"] += 1
    with pytest.raises(OrbitError) as info:
        await env.validate(prepared)
    assert info.value.status in {404, 409}
    assert not env.persisted and not env.events and not env.saved


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["expiry", "midnight", "future"])
async def test_final_database_time_rejects_expired_capture_or_cross_day(monkeypatch, damage):
    env = Environment(monkeypatch)
    if damage == "midnight":
        env.now = datetime(2026, 11, 8, 15, 59, tzinfo=UTC)
    prepared = await env.prepare()
    env.now += (
        timedelta(minutes=15)
        if damage == "expiry"
        else timedelta(minutes=2)
        if damage == "midnight"
        else -timedelta(seconds=1)
    )
    with pytest.raises(OrbitError) as info:
        await env.validate(prepared)
    assert info.value.code == "STALE_PREVIEW" and not env.persisted and not env.events


@pytest.mark.asyncio
async def test_missing_provider_503_and_no_write(monkeypatch):
    env = Environment(monkeypatch)
    env.store.provider = None
    with pytest.raises(OrbitError) as info:
        await env.prepare()
    assert info.value.status == 503 and not env.persisted and not env.events and not env.saved
    with pytest.raises(TypeError):
        ValidationAuthorityProvider()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "host,port,database",
    [
        ("localhost", 13306, None),
        ("127.0.0.1", 3306, None),
        ("127.0.0.1", 13306, "orbit"),
        ("127.0.0.1", 13306, "orbit_py_it_" + "x" * 32),
    ],
)
async def test_isolated_provider_rejected_outside_exact_database(monkeypatch, host, port, database):
    env = Environment(monkeypatch)
    env.provider.kind = "ISOLATED_TEST"
    with pytest.raises(OrbitError) as info:
        await env.store.require_provider(Session(env, host=host, port=port, database=database))
    assert info.value.status == 503


@pytest.mark.asyncio
async def test_isolated_provider_exact_guard_and_unknown_kind(monkeypatch):
    env = Environment(monkeypatch)
    env.provider.kind = "ISOLATED_TEST"
    assert await env.store.require_provider(env.pre_session) is env.provider
    env.provider.kind = "BROWSER_VERIFIED"
    with pytest.raises(OrbitError):
        await env.store.require_provider(env.pre_session)


@pytest.mark.parametrize(
    "damage",
    [
        "arbitrary_body",
        "path_id",
        "revision_bool",
        "duplicate",
        "too_many",
        "fingerprint",
        "mutable_errors",
        "verified_dict",
    ],
)
def test_observation_reference_whitelist_and_typed_evidence(monkeypatch, damage):
    env = Environment(monkeypatch)
    evidence = env.evidence
    if damage == "arbitrary_body":
        evidence = replace(evidence, observations=(ObservationReference("TOKEN", uid(1), 1),))
    elif damage == "path_id":
        evidence = replace(
            evidence,
            observations=(ObservationReference("MATERIAL", "https://secret.invalid/key", 1),),
        )
    elif damage == "revision_bool":
        evidence = replace(evidence, observations=(ObservationReference("ACCOUNT", uid(1), True),))
    elif damage == "duplicate":
        evidence = replace(evidence, observations=evidence.observations * 2)
    elif damage == "too_many":
        evidence = replace(
            evidence,
            observations=tuple(ObservationReference("ACCOUNT", uid(n + 1), 1) for n in range(4001)),
        )
    elif damage == "fingerprint":
        evidence = replace(evidence, fingerprint="arbitrary body")
    elif damage == "mutable_errors":
        evidence = replace(evidence, errors=[])
    else:
        evidence = {"verified": True}
    with pytest.raises(OrbitError) as info:
        _checked_evidence(evidence)
    assert info.value.status == 503


@pytest.mark.asyncio
async def test_persist_failure_never_audits_or_remembers_success(monkeypatch):
    env = Environment(monkeypatch)
    env.fail_persist = True
    with pytest.raises(RuntimeError):
        await env.validate(await env.prepare())
    assert not env.events and not env.saved
    # 替身不能证明SQL回滚：真实原子回滚必须由主线MySQL专项验收。


@pytest.mark.asyncio
async def test_csrf_token_decode_maps_to_403_and_no_provider_call(monkeypatch):
    env = Environment(monkeypatch)

    def invalid(*args):
        raise OrbitError(400, "TOKEN_INVALID", "受控纯测")

    monkeypatch.setattr("orbit_api.launch_validation_store.verify_csrf", invalid)
    with pytest.raises(OrbitError) as info:
        await env.prepare()
    assert info.value.status == 403 and "capture-outside" not in env.order


@pytest.mark.asyncio
async def test_hidden_object_does_not_replay_or_capture(monkeypatch):
    env = Environment(monkeypatch)
    env.saved = {"valid": True}
    hidden = AsyncMock(side_effect=OrbitError(404, "NOT_FOUND", "不可见"))
    monkeypatch.setattr("orbit_api.launch_validation_store.LaunchStore.row", hidden)
    with pytest.raises(OrbitError) as info:
        await env.prepare()
    assert info.value.status == 404 and "capture-outside" not in env.order


@pytest.mark.asyncio
async def test_revalidation_under_new_head_preserves_source_names_and_hash(monkeypatch):
    env = Environment(monkeypatch)
    first = await env.validate(await env.prepare())
    original_ids = (env.args["allocation"]["id"], env.args["name_reservation"]["id"])
    # 纯替身只模拟另一个幂等键尚无回执；真实双key并发由MySQL专项验证。
    env.saved = None
    env.source = replace(env.source, head_revision=8)
    env.now += timedelta(seconds=30)
    prepared = await env.store.prepare(
        lambda: env.pre_session,
        1,
        "会话纯测",
        "csrf纯测",
        "second-key-fixture",
        env.value,
        env.args["plan_id"],
        8,
    )
    result = await env.store.validate(
        env.final_session,
        1,
        "会话纯测",
        "csrf纯测",
        "second-key-fixture",
        env.value,
        env.args["plan_id"],
        8,
        uid(998),
        prepared,
    )
    assert first["hash"] == result["hash"]
    assert result["expires_at"] != first["expires_at"] and env.head["revision"] == 9
    assert [row["source"] for row in env.persisted] == [7, 7]
    assert [(row["allocation"], row["names"]) for row in env.persisted] == [
        original_ids,
        original_ids,
    ]


@pytest.mark.asyncio
async def test_cas_affected_rows_zero_no_audit_or_success_receipt(monkeypatch):
    env = Environment(monkeypatch)
    prepared = await env.prepare()
    env.update_count = 0
    with pytest.raises(OrbitError) as info:
        await env.validate(prepared)
    assert (
        info.value.code == "REVISION_CONFLICT"
        and not env.persisted
        and not env.events
        and not env.saved
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["missing_argument", "bad_field_error", "nonobject_allocation"])
async def test_provider_malformed_success_or_error_is_503_not_fake_user_validation(
    monkeypatch, damage
):
    env = Environment(monkeypatch)
    if damage == "missing_argument":
        env.evidence = replace(env.evidence, freeze_arguments_json=b"{}")
    elif damage == "bad_field_error":
        env.evidence = replace(
            env.evidence,
            errors=(ValidationIssue("not-a-pointer", "INVALID", "坏协议"),),
            freeze_arguments_json=None,
        )
    else:
        import json

        arguments = json.loads(env.evidence.freeze_arguments_json)
        arguments["allocation"] = []
        env.evidence = replace(env.evidence, freeze_arguments_json=canonical(arguments).encode())
    with pytest.raises(OrbitError) as info:
        await env.prepare()
    assert info.value.status == 503 and not env.persisted and not env.events and not env.saved


@pytest.mark.parametrize("raw", [b'{"scope_version":1,"scope_version":2}', b'{"amount":NaN}'])
def test_provider_duplicate_json_keys_and_nonfinite_numbers_are_not_silently_accepted(
    monkeypatch, raw
):
    env = Environment(monkeypatch)
    with pytest.raises(OrbitError) as info:
        _checked_evidence(replace(env.evidence, freeze_arguments_json=raw))
    assert info.value.status == 503


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "damage",
    ["asset", "revision", "account", "slot", "name", "sequence", "missing", "extra", "oversize"],
)
async def test_actual_persisted_items_must_match_even_when_header_hash_unchanged(
    monkeypatch, damage
):
    env = Environment(monkeypatch)
    prepared = await env.prepare()
    if damage == "asset":
        env.allocation_items[0]["asset_id"] = uid(999)
    elif damage == "revision":
        env.allocation_items[0]["asset_revision"] += 1
    elif damage == "account":
        env.allocation_items[0]["account_id"] = uid(999)
    elif damage == "slot":
        env.allocation_items[0]["slot_key"] += "/wrong"
    elif damage == "name":
        env.name_items[0]["name"] += "篡改"
    elif damage == "sequence":
        env.name_items[0]["sequence"] = "999"
    elif damage == "missing":
        env.allocation_items.pop()
    elif damage == "extra":
        env.name_items.append(copy.deepcopy(env.name_items[0]))
    else:
        env.allocation_items = env.allocation_items * 2501
    with pytest.raises(OrbitError) as info:
        await env.validate(prepared)
    assert info.value.code == "STALE_PREVIEW" and not env.persisted and not env.events


@pytest.mark.asyncio
async def test_actual_items_are_sets_by_stable_slot_and_database_decimal_sequence(monkeypatch):
    from decimal import Decimal

    env = Environment(monkeypatch)
    prepared = await env.prepare()
    env.allocation_items.reverse()
    env.name_items.reverse()
    for row in env.name_items:
        row["sequence"] = Decimal(row["sequence"])
    assert (await env.validate(prepared))["valid"]
    item_queries = [
        sql
        for sql, _ in env.calls
        if "FROM orbit_launch_allocation_item " in sql or "FROM orbit_launch_name_item " in sql
    ]
    assert len(item_queries) == 2 and all("LIMIT 10001 FOR SHARE" in sql for sql in item_queries)


def test_isolated_tools_case_inventory_and_exact_control_root(monkeypatch, tmp_path):
    import inspect
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    import launch_validation_checks as checks
    import launch_validation_fixture as fixture_module

    assert len(checks.LAUNCH_VALIDATION_BASELINE_CASES) == 5
    assert len(checks.LAUNCH_VALIDATION_CASES) == 16
    assert len(set(checks.LAUNCH_VALIDATION_BASELINE_CASES + checks.LAUNCH_VALIDATION_CASES)) == 21
    assert {"include_provider", "cipher", "control_dir"}.issubset(
        inspect.signature(checks.run_launch_validation_checks).parameters
    )
    root = tmp_path / ".runtime" / "launch-validation-control"
    monkeypatch.setattr(fixture_module, "CONTROL_ROOT", root)
    database = "orbit_py_it_" + "a" * 32
    selected = root / ("run-" + "b" * 32)
    assert fixture_module.control_directory(database, selected) == selected
    assert selected.is_dir()
    for invalid in (tmp_path / "outside", root / "run-not-uuid"):
        with pytest.raises(ValueError):
            fixture_module.control_directory(database, invalid)
    with pytest.raises(ValueError):
        fixture_module.control_directory("production", selected)


@pytest.mark.asyncio
async def test_isolated_tools_guard_cannot_run_in_business_database(monkeypatch):
    from pathlib import Path

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    from launch_validation_fixture import guard

    env = Environment(monkeypatch)
    with pytest.raises(OrbitError) as info:
        await guard(Session(env, database="production"))
    assert info.value.status == 503
