"""草稿指标依赖有序锁读纯测；不执行SQL，不把fixture当Meta来源验收。"""

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy import URL
from test_metric_profile_query import CURRENT, NOW, Result, row

import orbit_api.metric_profile_references as module
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.launch_contract import MAX_NODES

OWNERSHIP = {"owner_user_id": CURRENT.subject_id, "owner_team_id": CURRENT.team_id}


class Session:
    def __init__(
        self,
        rows=None,
        *,
        changed=None,
        owner=None,
        configurations=None,
        active=True,
        database=None,
        host="127.0.0.1",
        port=13306,
        revision=7,
    ):
        self.rows = [row()] if rows is None else rows
        self.changed = changed or {}
        self.owner = owner
        self.active = active
        self.database = database or "orbit_py_it_" + "a" * 32
        self.bind = SimpleNamespace(url=URL.create("mysql", host=host, port=port))
        self.revision = revision
        self.calls = []
        self.clock_seen = False
        self.configurations = configurations

    def in_transaction(self):
        return self.active

    async def execute(self, statement, values=None):
        sql = str(statement)
        self.calls.append((sql, values))
        if sql == "SELECT DATABASE()":
            return Result(self.database)
        if "FROM orbit_user_scope s" in sql:
            assert sql.endswith("FOR SHARE")
            return Result(
                self.owner
                if self.owner is not None
                else [
                    {
                        "tenant_id": CURRENT.tenant_id,
                        "data_role": "USER",
                        "subject_id": CURRENT.subject_id,
                        "team_id": CURRENT.team_id,
                    }
                ]
            )
        if "FROM orbit_system_configuration" in sql:
            assert not self.clock_seen, "clock后不能补锁新来源"
            assert values["ids"] == sorted(values["ids"]) and len(values["ids"]) <= 200
            assert sql.endswith("FOR SHARE")
            configurations = self.configurations
            if configurations is None:
                configurations = [
                    {
                        "id": item["source_config_id"],
                        "enabled": 1,
                        "revision": 2,
                        "section": "META_BM",
                    }
                    for item in self.rows
                    if item["source"] == "META"
                ]
            return Result([item for item in configurations if item["id"] in values["ids"]])
        if "FROM orbit_metric_profile_clock" in sql:
            self.clock_seen = True
            assert sql.endswith("FOR SHARE")
            return Result({"revision": self.revision, "now": NOW.replace(tzinfo=None)})
        assert "FROM orbit_metric_profile_head h" in sql
        assert values["ids"] == sorted(values["ids"]) and len(values["ids"]) <= 200
        selected = sorted(
            [item for item in self.rows if item["id"] in values["ids"]], key=lambda item: item["id"]
        )
        if "h.revision AS head_revision" not in sql:
            assert not self.clock_seen and "FOR SHARE" not in sql
            return Result(
                [
                    {
                        key: item[key]
                        for key in (
                            "id",
                            "current_version",
                            "source",
                            "source_config_id",
                            "source_config_revision",
                        )
                    }
                    for item in selected
                ]
            )
        assert self.clock_seen and "STRAIGHT_JOIN" in sql and sql.endswith("FOR SHARE")
        assert "orbit_system_configuration" not in sql
        return Result(
            [
                item | {"head_revision": 3, "state": "ENABLED"} | self.changed.get(item["id"], {})
                for item in selected
            ]
        )


@pytest.fixture
def authorize(monkeypatch):
    value = AsyncMock(return_value=CURRENT)
    monkeypatch.setattr(module, "require_business_access", value)
    return value


def call(session, ids=None, **kwargs):
    return asyncio.run(
        module.resolve_metric_profile_dependencies(
            session,
            CURRENT,
            2,
            OWNERSHIP,
            ids if ids is not None else [row()["id"]],
            permission=kwargs.pop("permission", "launch.create"),
            isolated_fixture=kwargs.pop("isolated_fixture", True),
            **kwargs,
        )
    )


@pytest.mark.parametrize(
    "permission", ["launch.create", "launch.edit", "templates.create", "templates.edit"]
)
def test_original_action_only_and_owner_without_any_read_menu_is_allowed(authorize, permission):
    session = Session()
    result = call(session, permission=permission)
    assert authorize.await_count == 1
    assert authorize.await_args.args[1:] == (CURRENT.actor_id, "launch", permission)
    dependency = result["metric_profiles"][row()["id"]]
    assert dependency == {
        "version": "exact-string-1",
        "head_revision": 3,
        "profile_hash": row()["payload_hash"],
        "source_sha256": "a" * 64,
        "source_config_id": None,
        "source_config_revision": None,
    }
    assert result["metric_profile_clock"] == 7
    assert "adapter_version" not in dependency and "attribution_spec" not in dependency
    owner_sql = [sql for sql, _ in session.calls if "FROM orbit_user_scope s" in sql][0]
    assert "launch.read" not in owner_sql and "sys_user_role" not in owner_sql


@pytest.mark.parametrize(
    "permission",
    [
        "launch.read",
        "launch.execute",
        "monitor.read",
        "template.create",
        "templates.read",
        "templates.share",
        "templates.archive",
    ],
)
def test_other_action_is_not_silently_substituted(authorize, permission):
    session = Session()
    with pytest.raises(ValueError):
        call(session, permission=permission)
    assert session.calls == []
    authorize.assert_not_awaited()


def test_empty_draft_without_fixture_has_zero_source_queries_or_extra_auth(authorize):
    session = Session([])
    assert call(session, [], isolated_fixture=False) == {"metric_profiles": {}}
    assert session.calls == []
    authorize.assert_not_awaited()


@pytest.mark.parametrize(
    "host,port,database",
    [("localhost", 13306, None), ("127.0.0.1", 3306, None), ("127.0.0.1", 13306, "production")],
)
def test_explicit_fixture_guard_also_applies_to_empty_ids(authorize, host, port, database):
    with pytest.raises(OrbitError) as error:
        call(Session([], host=host, port=port, database=database), [])
    assert error.value.status == 503
    authorize.assert_not_awaited()


def test_default_production_mode_rejects_fixture_rows(authorize):
    with pytest.raises(OrbitError) as error:
        call(Session(), isolated_fixture=False)
    assert error.value.status == 503


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", str(UUID(int=999))),
        ("subject_id", str(UUID(int=998))),
        ("team_id", str(UUID(int=997))),
        ("data_role", "UNKNOWN"),
    ],
)
def test_owner_current_identity_and_ownership_are_rechecked(authorize, field, value):
    owner = {
        "tenant_id": CURRENT.tenant_id,
        "subject_id": CURRENT.subject_id,
        "team_id": CURRENT.team_id,
        "data_role": "USER",
    } | {field: value}
    with pytest.raises(OrbitError) as error:
        call(Session(owner=[owner]))
    assert error.value.status == 404


def test_disabled_or_invited_owner_has_no_current_row(authorize):
    with pytest.raises(OrbitError) as error:
        call(Session(owner=[]))
    assert error.value.status == 404


@pytest.mark.parametrize(
    "field,value",
    [
        ("current_version", "changed"),
        ("source_config_id", str(UUID(int=999))),
        ("source_config_revision", 99),
        ("source", "META"),
        ("state", "DISABLED"),
    ],
)
def test_change_after_metadata_cannot_cause_clock_after_source_lock(authorize, field, value):
    session = Session(changed={row()["id"]: {field: value}})
    with pytest.raises(OrbitError) as error:
        call(session)
    assert error.value.status == 409 and error.value.code == "METRIC_PROFILE_SOURCE_CHANGED"
    assert not any("FROM orbit_system_configuration" in sql for sql, _ in session.calls)


@pytest.mark.parametrize(
    "field,value",
    [
        ("payload_hash", "b" * 64),
        ("source_proof_json", '{"bad":true}'),
        ("observed_at", datetime(2026, 11, 1, second=1)),
        ("head_revision", 0),
    ],
)
def test_bad_proof_hash_observation_or_revision_never_returns_partial_result(
    authorize, field, value
):
    good, bad = row(1), row(2)
    session = Session([good, bad], changed={bad["id"]: {field: value}})
    with pytest.raises(OrbitError) as error:
        call(session, [good["id"], bad["id"]])
    assert error.value.status == 503


def test_missing_active_head_is_not_partial_success(authorize):
    with pytest.raises(OrbitError) as error:
        call(Session(), [row(1)["id"], row(2)["id"]])
    assert error.value.status == 404


def test_five_hundred_profiles_and_sources_use_global_uuid_order_and_bounded_batches(authorize):
    rows = []
    for index in range(1, 501):
        value = row(index, source="META")
        source_id = str(UUID(int=10500 - index))
        value["source_config_id"] = source_id
        proof = json.loads(value["source_proof_json"]) | {"source_config_id": source_id}
        value["source_proof_json"] = canonical(proof)
        rows.append(value)
    session = Session(rows)
    result = call(session, [value["id"] for value in reversed(rows)], isolated_fixture=False)
    assert len(result["metric_profiles"]) == 500
    configs = [
        (sql, values) for sql, values in session.calls if "FROM orbit_system_configuration" in sql
    ]
    heads = [(sql, values) for sql, values in session.calls if "h.revision AS head_revision" in sql]
    assert [len(values["ids"]) for _, values in configs] == [200, 200, 100]
    assert [len(values["ids"]) for _, values in heads] == [200, 200, 100]
    assert [identifier for _, values in configs for identifier in values["ids"]] == sorted(
        value["source_config_id"] for value in rows
    )
    assert [identifier for _, values in heads for identifier in values["ids"]] == sorted(
        value["id"] for value in rows
    )


@pytest.mark.parametrize(
    "source",
    [
        [],
        [
            {
                "id": row(source="META")["source_config_id"],
                "section": "META_BM",
                "revision": 3,
                "enabled": 1,
            }
        ],
        [
            {
                "id": row(source="META")["source_config_id"],
                "section": "META_BM",
                "revision": 2,
                "enabled": 0,
            }
        ],
    ],
)
def test_revoked_or_missing_configuration_fails_before_clock(authorize, source):
    session = Session([row(source="META")], configurations=source)
    with pytest.raises(OrbitError) as error:
        call(session, isolated_fixture=False)
    assert error.value.code == "METRIC_PROFILE_SOURCE_CHANGED" and not session.clock_seen


def test_collects_only_original_adset_fields_and_deduplicates_uuid():
    left, right = row(1)["id"], row(2)["id"]
    campaigns = [
        {
            "adsets": [
                {"metric_profile_id": right},
                {"metric_profile_id": None},
                {"metric_profile_id": left},
                {"metric_profile_id": right},
            ]
        }
    ]
    assert module.collect_metric_profile_ids(campaigns) == [left, right]
    assert module.MAX_NODES == MAX_NODES


def test_original_plan_node_budget_not_an_invented_profile_limit(authorize):
    with pytest.raises(OrbitError) as error:
        call(Session(), [row()["id"]] * (MAX_NODES + 1))
    assert error.value.code == "PLAN_NODE_LIMIT"
    with pytest.raises(OrbitError) as error:
        module.collect_metric_profile_ids([{"adsets": [{}] * (MAX_NODES + 1)}])
    assert error.value.code == "PLAN_NODE_LIMIT"


def test_caller_context_change_rejected_before_any_profile_lock(authorize):
    from dataclasses import replace

    authorize.return_value = replace(CURRENT, data_role="TEAM_ADMIN")
    session = Session()
    with pytest.raises(OrbitError) as error:
        call(session)
    assert error.value.status == 403
    assert not any("FROM orbit_metric_profile_head" in sql for sql, _ in session.calls)


def test_no_outer_transaction_is_rejected_before_database(authorize):
    session = Session(active=False)
    with pytest.raises(ValueError):
        call(session)
    assert session.calls == []


@pytest.mark.parametrize(
    "permission", ["launch.create", "launch.edit", "templates.create", "templates.edit"]
)
def test_revoked_original_caller_action_is_not_replaced_with_any_read(authorize, permission):
    authorize.side_effect = OrbitError(403, "PERMISSION_DENIED", "当前动作已撤销")
    session = Session()
    with pytest.raises(OrbitError) as error:
        call(session, permission=permission)
    assert error.value.status == 403
    assert authorize.await_args.args[1:] == (CURRENT.actor_id, "launch", permission)
    assert not any("FROM orbit_metric_profile_head" in sql for sql, _ in session.calls)


@pytest.mark.parametrize("revision", [None, 0, True, 9007199254740992])
def test_invalid_metric_clock_is_not_invented_or_defaulted(authorize, revision):
    with pytest.raises(OrbitError) as error:
        call(Session(revision=revision))
    assert (
        error.value.status == 503 and error.value.code == "METRIC_PROFILE_INITIALIZATION_REQUIRED"
    )


def test_corrupt_database_source_uuid_fails_closed_as_source_error(authorize):
    broken = row(source="META") | {"source_config_id": "not-a-uuid"}
    with pytest.raises(OrbitError) as error:
        call(Session([broken]), isolated_fixture=False)
    assert error.value.status == 503


def test_final_missing_row_is_source_change_not_partial_result(authorize, monkeypatch):
    original = Session.execute

    async def missing(self, statement, values=None):
        if "h.revision AS head_revision" in str(statement):
            return Result([])
        return await original(self, statement, values)

    monkeypatch.setattr(Session, "execute", missing)
    with pytest.raises(OrbitError) as error:
        call(Session())
    assert error.value.code == "METRIC_PROFILE_SOURCE_CHANGED"


@pytest.mark.parametrize("permission", ["templates.create", "templates.edit"])
def test_template_only_action_is_never_mapped_to_additional_plan_permissions(authorize, permission):
    async def exact_action(_session, actor, menu, action):
        assert actor == CURRENT.actor_id and menu == "launch"
        if action != permission:
            raise OrbitError(403, "PERMISSION_DENIED", "仅授予该模板动作")
        return CURRENT

    authorize.side_effect = exact_action
    assert call(Session(), permission=permission)["metric_profiles"]
    assert authorize.await_count == 1
    assert authorize.await_args.args[1:] == (CURRENT.actor_id, "launch", permission)
