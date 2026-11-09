"""短事务/绑定边界的受控替身测试；不证明真实SQL权限或Meta联通。"""

import json
from dataclasses import FrozenInstanceError, replace
from urllib.parse import urlsplit
from uuid import uuid4

import pytest

import orbit_api.meta_bound_observation as module
from orbit_api.authorization import BusinessContext
from orbit_api.errors import OrbitError
from orbit_api.meta_launch_observation import GraphReadResponse, MetaObservationFailure


def uid():
    return str(uuid4())


class Result:
    def __init__(self, value):
        self.value = value

    def mappings(self):
        return self

    def __iter__(self):
        return iter(self.value)

    def scalar_one_or_none(self):
        return self.value


class Transaction:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        self.session.active = True
        self.session.events.append("begin")

    async def __aexit__(self, kind, *_):
        self.session.active = False
        self.session.events.append("rollback" if kind else "commit")


class Session:
    def __init__(self, current):
        self.current, self.active, self.closed = current, False, False
        self.events, self.sql = [], []
        self.managed = []
        self.auth_version = 9
        self.accounts = [
            dict(
                tenant_id=current.tenant_id,
                id=uid(),
                revision=5,
                external_id="001",
                owner_user_id=current.subject_id,
                owner_team_id=current.team_id,
                unbound_at=None,
            )
        ]
        self.sources = [
            dict(
                id=uid(),
                revision=7,
                settings_json={"businessId": "123", "graphVersion": "v23.0"},
                secrets_json={"accessToken": "encrypted-only"},
            )
        ]

    async def __aenter__(self):
        self.events.append("open")
        return self

    async def __aexit__(self, *_):
        self.closed = True
        self.events.append("close")

    def in_transaction(self):
        return self.active

    def begin(self):
        return Transaction(self)

    async def execute(self, statement, parameters):
        assert self.active
        sql = str(statement)
        self.sql.append((sql, parameters))
        if "sys_identity_subject" in sql:
            self.events.append("auth_version")
            return Result(self.auth_version)
        if "orbit_ad_account" in sql:
            assert parameters["tenant"] == self.current.tenant_id
            assert "ORDER BY a.id LIMIT 501 FOR SHARE OF a" in sql
            self.events.append("accounts")
            return Result(self.accounts)
        if "orbit_system_configuration" in sql:
            assert parameters == {"tenant": self.current.tenant_id}
            assert "section='META_BM'" in sql and "verification_status='READ_VERIFIED'" in sql
            assert "LIMIT 2 FOR SHARE" in sql
            self.events.append("configuration")
            return Result(self.sources)
        raise AssertionError("不允许额外SQL或写入")


class Cipher:
    ready = True

    def __init__(self):
        self.calls = []

    def decrypt_internal(self, *args):
        self.calls.append(args)
        return "very-secret-token"


class Transport:
    def __init__(self, session):
        self.session, self.calls = session, []

    async def get(self, target, headers, *, maximum_bytes):
        assert self.session.closed and not self.session.in_transaction()
        assert self.session.events[-1] == "close"
        assert headers["Authorization"] == "Bearer very-secret-token"
        assert "very-secret-token" not in target
        self.calls.append(target)
        path = urlsplit(target).path.removeprefix("/v23.0/")
        if path == "123/owned_ad_accounts":
            value = {
                "data": [
                    {"id": "act_" + row["external_id"], "account_id": row["external_id"]}
                    for row in self.session.accounts
                ]
            }
        elif path == "123/client_ad_accounts":
            value = {"data": []}
        elif "/" not in path and path.startswith("act_"):
            value = {"id": path, "account_id": path[4:], "name": "原名" * 1500}
        elif path.endswith("/promote_pages"):
            value = {"data": [{"id": "009", "name": "页" * 4096}]}
        else:
            value = {"data": []}
        return GraphReadResponse(200, json.dumps(value).encode())


@pytest.fixture
def setup(monkeypatch):
    current = BusinessContext(23, uid(), "USER", uid(), uid())
    session, cipher = Session(current), Cipher()

    async def access(selected, actor, menu, permission):
        assert selected is session and selected.active
        assert (actor, menu, permission) == (23, "accounts", "accounts.sync")
        selected.events.append("authorize")
        return current

    async def clock(selected, selected_current):
        assert selected is session and selected_current == current
        selected.events.append("clock_dueguard")
        return 11

    async def managed(selected, selected_current):
        selected.events.append("managed_current")
        return selected.managed

    monkeypatch.setattr(module, "require_business_access", access)
    monkeypatch.setattr(module, "clock", clock)
    monkeypatch.setattr(module, "managed_teams", managed)
    return current, session, cipher


async def capture(setup, **kwargs):
    current, session, cipher = setup
    return await module.capture_meta_source(
        lambda: session,
        current.actor_id,
        [row["id"] for row in session.accounts],
        cipher=cipher,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_real_observer_protocol_runs_only_after_owned_transaction_and_session_exit(setup):
    current, session, cipher = setup
    snapshot = await capture(setup)
    assert session.events == [
        "open",
        "begin",
        "authorize",
        "auth_version",
        "clock_dueguard",
        "managed_current",
        "accounts",
        "configuration",
        "commit",
        "close",
    ]
    bound = await module.observe_meta_source(snapshot, transport=Transport(session))
    assert (snapshot.tenant_id, snapshot.actor_id, snapshot.subject_id, snapshot.team_id) == (
        current.tenant_id,
        23,
        current.subject_id,
        current.team_id,
    )
    assert snapshot.auth_version == 9 and snapshot.account_clock == 11
    assert snapshot.accounts[0].account_revision == 5
    assert snapshot.accounts[0].external_id == "001"
    assert snapshot.configuration.source_config_revision == 7
    assert cipher.calls == [
        ("encrypted-only", current.tenant_id, session.sources[0]["id"], "accessToken")
    ]
    observed = bound.observation.accounts[0]
    assert json.loads(observed.metadata_json)["name"] == "原名" * 1500
    assert len(observed.resources[0].name) == 4096
    assert bound.observation.execution_authorized is False
    assert (
        not bound.publication_revalidated and not bound.durable and not bound.execution_authorized
    )
    assert "very-secret-token" not in repr(snapshot) + repr(bound) + repr(snapshot.configuration)
    with pytest.raises(FrozenInstanceError):
        bound.durable = True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [("tenant_id", uid()), ("subject_id", uid()), ("auth_version", 10), ("account_clock", 12)],
)
async def test_replaced_snapshot_binding_rejected_before_any_network(setup, field, value):
    snapshot = replace(await capture(setup), **{field: value})
    transport = Transport(setup[1])
    with pytest.raises(OrbitError, match="只读来源"):
        await module.observe_meta_source(snapshot, transport=transport)
    assert not transport.calls


@pytest.mark.asyncio
async def test_config_and_account_revision_changes_cannot_reuse_binding_digest(setup):
    snapshot = await capture(setup)
    replacements = [
        replace(snapshot, configuration=replace(snapshot.configuration, source_config_revision=8)),
        replace(snapshot, configuration=replace(snapshot.configuration, business_id="456")),
        replace(snapshot, accounts=(replace(snapshot.accounts[0], account_revision=6),)),
    ]
    for changed in replacements:
        with pytest.raises(OrbitError):
            await module.observe_meta_source(changed, transport=Transport(setup[1]))


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 2])
async def test_zero_or_multiple_current_sources_fail_without_decrypt_or_network(setup, count):
    _, session, cipher = setup
    session.sources *= count
    with pytest.raises(OrbitError) as failure:
        await capture(setup)
    assert failure.value.code == "META_BOUND_SOURCE_UNAVAILABLE" and not cipher.calls
    assert session.events[-2:] == ["rollback", "close"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [("tenant_id", uid()), ("unbound_at", "known-unbound"), ("revision", True), ("external_id", 1)],
)
async def test_corrupt_or_unbound_account_never_reaches_configuration(setup, field, value):
    setup[1].accounts[0][field] = value
    with pytest.raises(OrbitError):
        await capture(setup)
    assert "configuration" not in setup[1].events


@pytest.mark.asyncio
async def test_missing_scope_account_is_not_found_not_partial_success(setup):
    current, session, cipher = setup
    with pytest.raises(OrbitError) as failure:
        await module.capture_meta_source(lambda: session, current.actor_id, [uid()], cipher=cipher)
    assert failure.value.status == 404
    assert "configuration" not in session.events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "settings",
    [
        {"businessId": "123", "apiVersion": "v23.0"},
        {"businessId": 123, "graphVersion": "v23.0"},
        [],
    ],
)
async def test_config_uses_actual_graphversion_and_businessid_no_guessed_fallback(setup, settings):
    setup[1].sources[0]["settings_json"] = settings
    with pytest.raises(OrbitError) as failure:
        await capture(setup)
    assert failure.value.code == "META_BOUND_SOURCE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_cipher_failure_is_sanitized_without_secret_context(setup):
    def decrypt(*args):
        raise RuntimeError("private-token-in-third-party-error")

    setup[2].decrypt_internal = decrypt
    with pytest.raises(OrbitError) as failure:
        await capture(setup)
    assert "private-token" not in str(failure.value)
    assert failure.value.__suppress_context__


@pytest.mark.asyncio
async def test_current_permission_revocation_stops_capture_and_no_extra_read_is_requested(
    setup, monkeypatch
):
    async def denied(*args):
        raise OrbitError(403, "PERMISSION_DENIED", "撤销同步")

    monkeypatch.setattr(module, "require_business_access", denied)
    with pytest.raises(OrbitError) as failure:
        await capture(setup)
    assert failure.value.status == 403 and not setup[1].sql


@pytest.mark.asyncio
@pytest.mark.parametrize("permission", ["accounts.read", "launch.edit", "launch.execute"])
async def test_unimplemented_permission_branches_are_rejected_before_open(setup, permission):
    with pytest.raises(ValueError):
        await capture(setup, permission=permission)
    assert not setup[1].events


@pytest.mark.asyncio
async def test_caller_transaction_is_never_reused_or_committed(setup):
    setup[1].active = True
    with pytest.raises(ValueError):
        await capture(setup)
    assert "commit" not in setup[1].events and "begin" not in setup[1].events


@pytest.mark.asyncio
async def test_later_database_mutation_does_not_silently_refresh_frozen_capture_or_claim_cas(setup):
    snapshot = await capture(setup)
    setup[1].accounts[0]["revision"] += 1
    setup[1].sources[0]["revision"] += 1
    bound = await module.observe_meta_source(snapshot, transport=Transport(setup[1]))
    assert bound.source.accounts[0].account_revision == 5
    assert bound.source.configuration.source_config_revision == 7
    assert not bound.publication_revalidated


@pytest.mark.asyncio
async def test_selection_upper_bound_duplicate_and_empty_rejected_without_network(setup):
    current, session, cipher = setup
    for values in ([], [uid() for _ in range(501)], [session.accounts[0]["id"]] * 2):
        with pytest.raises(OrbitError):
            await module.capture_meta_source(
                lambda: session, current.actor_id, values, cipher=cipher
            )
    assert not session.events


@pytest.mark.asyncio
async def test_500_accounts_are_frozen_by_one_bounded_sorted_query_not_n_plus_one(setup):
    current, session, _ = setup
    session.accounts = [
        dict(session.accounts[0], id=uid(), external_id=f"{index:05d}") for index in range(500)
    ]
    snapshot = await capture(setup)
    assert len(snapshot.accounts) == 500
    assert [row.account_id for row in snapshot.accounts] == sorted(
        row["id"] for row in session.accounts
    )
    assert len(session.sql) == 3  # auth版本、一次账户集合、一次配置；clock替身另记。
    assert snapshot.tenant_id == current.tenant_id


@pytest.mark.asyncio
async def test_observer_incomplete_failure_never_returns_bound_success(setup):
    class EmptyBm(Transport):
        async def get(self, *args, **kwargs):
            return GraphReadResponse(200, b'{"data":[]}')

    with pytest.raises(MetaObservationFailure) as failure:
        await module.observe_meta_source(await capture(setup), transport=EmptyBm(setup[1]))
    assert failure.value.code == "META_ACCOUNT_NOT_OBSERVED_IN_BM"


@pytest.mark.asyncio
async def test_due_projection_guard_failure_stops_before_account_and_source_locks(
    setup, monkeypatch
):
    async def lag(*args):
        raise OrbitError(503, "ACCOUNT_ASSIGNMENT_PROJECTION_LAG", "到期归属待处理")

    monkeypatch.setattr(module, "clock", lag)
    with pytest.raises(OrbitError) as failure:
        await capture(setup)
    assert failure.value.code == "ACCOUNT_ASSIGNMENT_PROJECTION_LAG"
    assert "accounts" not in setup[1].events and "configuration" not in setup[1].events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("source_config_id", uid()),
        ("source_config_revision", 8),
        ("business_id", "456"),
        ("api_version", "v24.0"),
    ],
)
async def test_returned_observer_source_must_still_match_bound_config(
    setup, monkeypatch, field, value
):
    snapshot = await capture(setup)
    actual = await module.MetaLaunchObserver(
        snapshot.configuration, transport=Transport(setup[1])
    ).observe(["001"])

    class MismatchedObserver:
        def __init__(self, *args, **kwargs):
            pass

        async def observe(self, identifiers):
            return replace(actual, **{field: value})

    monkeypatch.setattr(module, "MetaLaunchObserver", MismatchedObserver)
    with pytest.raises(OrbitError) as failure:
        await module.observe_meta_source(snapshot)
    assert failure.value.code == "META_BOUND_SOURCE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_multi_account_uuid_order_and_external_id_order_are_not_confused(setup):
    _, session, _ = setup
    first = session.accounts[0]
    session.accounts = [
        dict(first, id="00000000-0000-0000-0000-000000000001", external_id="999"),
        dict(first, id="00000000-0000-0000-0000-000000000002", external_id="001"),
    ]
    bound = await module.observe_meta_source(await capture(setup), transport=Transport(session))
    assert [row.external_id for row in bound.source.accounts] == ["999", "001"]
    assert [row.external_id for row in bound.observation.accounts] == ["001", "999"]


@pytest.mark.asyncio
@pytest.mark.parametrize("managed", [False, True])
async def test_team_capture_requires_current_explicit_managed_set_not_nested_exists(
    setup, monkeypatch, managed
):
    current, session, _ = setup
    team_current = replace(current, data_role="TEAM_ADMIN")
    session.accounts[0]["owner_user_id"] = uid()
    session.managed = [current.team_id] if managed else []

    async def authorized(*args):
        return team_current

    async def clock(*args):
        return 11

    monkeypatch.setattr(module, "require_business_access", authorized)
    monkeypatch.setattr(module, "clock", clock)
    if managed:
        snapshot = await capture(setup)
        assert snapshot.data_role == "TEAM_ADMIN"
    else:
        with pytest.raises(OrbitError) as failure:
            await capture(setup)
        assert failure.value.status == 404
    assert "managed_current" in session.events
    assert all("EXISTS(" not in sql for sql, _ in session.sql)
