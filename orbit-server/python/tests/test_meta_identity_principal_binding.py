"""M3b短事务/CAS/主体绑定纯协议；替身不是真实配置、SQL或Meta权限证明。"""

from dataclasses import FrozenInstanceError, replace
from uuid import uuid4

import pytest
from test_meta_identity_facts_observation import Transport, selected
from test_meta_identity_facts_observation import bound as bound

import orbit_api.meta_identity_principal_binding as module
from orbit_api.authorization import BusinessContext
from orbit_api.errors import OrbitError
from orbit_api.meta_launch_observation import GraphReadResponse
from orbit_api.meta_observation_registry import digest, stream_digest


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

    async def __aexit__(self, kind, *_args):
        self.session.active = False
        self.session.events.append("rollback" if kind else "commit")


class Session:
    def __init__(self, bound):
        old = bound.source
        self.current = BusinessContext(
            old.actor_id, old.tenant_id, old.data_role, old.subject_id, old.team_id
        )
        self.version, self.watermark, self.managed = old.auth_version, old.account_clock, []
        self.sources = [
            dict(
                id=old.configuration.source_config_id,
                revision=old.configuration.source_config_revision,
                settings_json=dict(
                    businessId=old.configuration.business_id,
                    graphVersion=old.configuration.api_version,
                    systemUserId="00042",
                ),
                secrets_json={"accessToken": "encrypted-real-fixture"},
            )
        ]
        self.accounts = [
            dict(
                tenant_id=old.tenant_id,
                id=row.account_id,
                revision=row.account_revision,
                external_id=row.external_id,
                owner_user_id=row.owner_user_id,
                owner_team_id=row.owner_team_id,
                unbound_at=None,
            )
            for row in old.accounts
        ]
        self.active, self.closed, self.events, self.sql = False, False, [], []

    async def __aenter__(self):
        self.events.append("open")
        return self

    async def __aexit__(self, *_args):
        self.closed = True
        self.events.append("close")

    def in_transaction(self):
        return self.active

    def begin(self):
        return Transaction(self)

    async def execute(self, statement, params):
        assert self.active and not self.closed
        sql = str(statement)
        self.sql.append((sql, params))
        if "sys_identity_subject" in sql:
            assert "FOR SHARE" in sql
            self.events.append("auth_version")
            return Result(self.version)
        if "orbit_system_configuration" in sql:
            assert "FORCE INDEX(PRIMARY)" in sql and "ORDER BY id FOR SHARE" in sql
            assert "enabled=1" in sql and "verification_status='READ_VERIFIED'" in sql
            self.events.append("configurations")
            return Result(self.sources)
        if "orbit_ad_account" in sql:
            assert "ORDER BY a.id LIMIT 501 FOR SHARE OF a" in sql
            assert "EXISTS" not in sql
            assert set(params["ids"]) == {row["id"] for row in self.accounts}
            self.events.append("accounts")
            return Result(self.accounts)
        raise AssertionError("未声明的SQL")


@pytest.fixture
def setup(bound, monkeypatch):
    session = Session(bound)

    async def access(selected_session, actor, menu, action):
        assert selected_session is session and selected_session.active
        assert (actor, menu, action) == (bound.source.actor_id, "accounts", "accounts.sync")
        session.events.append("authorize")
        return session.current

    async def clock(selected_session, current):
        assert selected_session is session and current is session.current
        session.events.append("clock_dueguard")
        return session.watermark

    async def managed(selected_session, current):
        assert selected_session is session and current is session.current
        session.events.append("managed_current_lock")
        return session.managed

    monkeypatch.setattr(module, "require_business_access", access)
    monkeypatch.setattr(module, "clock", clock)
    monkeypatch.setattr(module, "managed_teams", managed)
    return bound, session


async def capture(setup):
    bound, session = setup
    return await module.capture_identity_principal(lambda: session, bound.source.actor_id, bound)


async def test_real_configuration_value_bound_after_complete_current_cas_then_session_closed(setup):
    bound, session = setup
    source = await capture(setup)
    assert source.system_user_id == "00042"
    assert source.bound is bound and source.source_sha256 == module.source_hash(source)
    assert session.closed and not session.in_transaction()
    assert session.events == [
        "open",
        "begin",
        "authorize",
        "auth_version",
        "configurations",
        "clock_dueguard",
        "managed_current_lock",
        "accounts",
        "commit",
        "close",
    ]
    assert bound.source.configuration.token not in repr(source)
    with pytest.raises(FrozenInstanceError):
        source.system_user_id = "5"


async def test_actual_me_match_does_not_grant_type_permissions_or_publish_authority(setup):
    bound, session = setup
    source = await capture(setup)

    class ClosedTransport(Transport):
        async def get(self, *args, **kwargs):
            assert session.closed and not session.in_transaction()
            assert session.events[-1] == "close"
            return await super().get(*args, **kwargs)

    before_sql = len(session.sql)
    match = await module.observe_identity_principal(
        source, [selected(bound)], transport=ClosedTransport()
    )
    assert match.principal_id == source.system_user_id == "00042"
    assert match.principal_matches is True
    assert match.principal_type_verified is match.execution_authorized is match.durable is False
    assert match.publication_revalidated is False
    assert match.capability_version is match.policy_version is None
    assert match.facts.principal_binding == "CONFIG_PRINCIPAL_NOT_BOUND"
    assert "usable" not in match.__dict__ and "verified" not in match.__dict__
    assert len(session.sql) == before_sql
    assert bound.source.configuration.token not in repr(match)
    assert len(match.evidence_sha256) == 64


@pytest.mark.parametrize("value", [None, "", 42, True, "42/x", "4\0", "\ud800"])
async def test_missing_or_invalid_configured_principal_503_without_synthetic_expected(setup, value):
    _bound, session = setup
    session.sources[0]["settings_json"]["systemUserId"] = value
    with pytest.raises(OrbitError) as error:
        await capture(setup)
    assert (error.value.status, error.value.code) == (503, "META_PRINCIPAL_SOURCE_UNAVAILABLE")
    assert session.events[-2:] == ["rollback", "close"]


@pytest.mark.parametrize(
    "change", ["none", "multiple", "id", "revision", "business", "version", "secret"]
)
async def test_config_selection_and_exact_fields_checked_not_only_source_id(setup, change):
    _bound, session = setup
    if change == "none":
        session.sources = []
    elif change == "multiple":
        session.sources.append(dict(session.sources[0]))
    elif change == "id":
        session.sources[0]["id"] = str(uuid4())
    elif change == "revision":
        session.sources[0]["revision"] += 1
    elif change == "business":
        session.sources[0]["settings_json"]["businessId"] = "999"
    elif change == "version":
        session.sources[0]["settings_json"]["graphVersion"] = "v24.0"
    else:
        session.sources[0]["secrets_json"] = {}
    with pytest.raises(OrbitError) as error:
        await capture(setup)
    assert error.value.status == (503 if change in {"none", "multiple", "secret"} else 409)


@pytest.mark.parametrize(
    "change",
    ["auth", "clock", "subject", "team", "role", "revision", "external", "owner_team", "unbound"],
)
async def test_second_short_transaction_rechecks_entire_scope_and_account_versions(setup, change):
    _bound, session = setup
    if change == "auth":
        session.version += 1
    elif change == "clock":
        session.watermark += 1
    elif change in {"subject", "team", "role"}:
        key = {"subject": "subject_id", "team": "team_id", "role": "data_role"}[change]
        session.current = replace(
            session.current, **{key: "SUPER_ADMIN" if change == "role" else str(uuid4())}
        )
    elif change == "revision":
        session.accounts[0]["revision"] += 1
    elif change == "external":
        session.accounts[0]["external_id"] = "002"
    elif change == "owner_team":
        session.accounts[0]["owner_team_id"] = str(uuid4())
    else:
        session.accounts[0]["unbound_at"] = "explicit-unbound"
    with pytest.raises(OrbitError) as error:
        await capture(setup)
    assert error.value.status in {404, 409}
    assert session.events[-2:] == ["rollback", "close"]


async def test_current_actor_tenant_not_caller_supplied_bound_scope(setup):
    _bound, session = setup
    session.current = replace(session.current, tenant_id=str(uuid4()))
    with pytest.raises(OrbitError) as error:
        await capture(setup)
    assert error.value.status == 403
    assert "configurations" not in session.events


async def test_wrong_actor_rejected_before_opening_factory(setup):
    bound, session = setup
    with pytest.raises(OrbitError) as error:
        await module.capture_identity_principal(lambda: session, bound.source.actor_id + 1, bound)
    assert error.value.status == 403 and session.events == []


async def test_existing_outer_transaction_never_committed_or_rolled_back(setup):
    _bound, session = setup
    session.active = True
    with pytest.raises(ValueError):
        await capture(setup)
    assert session.events == [] and session.active and not session.closed


async def test_dueguard_error_preserved_no_network_or_scope_bypass(setup, monkeypatch):
    async def blocked(*_args):
        raise OrbitError(503, "ACCOUNT_PROJECTION_NOT_CURRENT", "归属尚未追平")

    monkeypatch.setattr(module, "clock", blocked)
    with pytest.raises(OrbitError) as error:
        await capture(setup)
    assert error.value.code == "ACCOUNT_PROJECTION_NOT_CURRENT"


@pytest.mark.parametrize("mutation", ["issuer", "user", "root"])
async def test_captured_principal_source_tamper_rejected_before_get(setup, mutation):
    bound, _session = setup
    source = await capture(setup)
    source = {
        "issuer": replace(source, _issuer=object()),
        "user": replace(source, system_user_id="999"),
        "root": replace(source, source_sha256="a" * 64),
    }[mutation]
    transport = Transport()
    with pytest.raises(OrbitError) as error:
        await module.observe_identity_principal(source, [selected(bound)], transport=transport)
    assert error.value.status == 503 and transport.calls == []


@pytest.mark.parametrize(
    "principal,expected", [("42", "META_PRINCIPAL_MISMATCH"), (None, "META_PRINCIPAL_NOT_OBSERVED")]
)
async def test_me_precise_string_match_and_missing_does_not_default_to_config(
    setup, principal, expected
):
    bound, _session = setup
    source = await capture(setup)

    def hook(url, _number):
        if url.path.endswith("/me"):
            return GraphReadResponse(200, ("{}" if principal is None else '{"id":"42"}').encode())
        return None

    with pytest.raises(OrbitError) as error:
        await module.observe_identity_principal(
            source, [selected(bound)], transport=Transport(hook)
        )
    assert (error.value.status, error.value.code) == (503, expected)


async def test_old_match_is_not_silently_revalidated_by_later_configuration_changes(setup):
    bound, session = setup
    source = await capture(setup)
    session.sources[0]["revision"] += 1
    match = await module.observe_identity_principal(
        source, [selected(bound)], transport=Transport()
    )
    assert match.publication_revalidated is match.execution_authorized is False
    assert match.source.bound.source.configuration.source_config_revision == 7


def rebind(bound, source):
    import orbit_api.meta_bound_observation as binding_module

    source = replace(source, binding_sha256=binding_module.binding_hash(source))
    return replace(
        bound,
        source=source,
        binding_sha256=digest([source.binding_sha256, bound.observation.evidence_sha256]),
    )


async def test_current_managed_team_required_and_never_nested_old_view(setup):
    original_bound, session = setup
    old = original_bound.source
    accounts = (replace(old.accounts[0], owner_user_id=str(uuid4())),)
    bound = rebind(original_bound, replace(old, data_role="TEAM_ADMIN", accounts=accounts))
    session.current = replace(session.current, data_role="TEAM_ADMIN")
    session.accounts[0]["owner_user_id"] = accounts[0].owner_user_id
    session.managed = []
    with pytest.raises(OrbitError) as error:
        await module.capture_identity_principal(lambda: session, old.actor_id, bound)
    assert error.value.status == 404
    assert "managed_current_lock" in session.events


async def test_explicit_current_managed_team_allows_existing_bound_without_extra_actions(setup):
    original_bound, session = setup
    old = original_bound.source
    accounts = (replace(old.accounts[0], owner_user_id=str(uuid4())),)
    bound = rebind(original_bound, replace(old, data_role="TEAM_ADMIN", accounts=accounts))
    session.current = replace(session.current, data_role="TEAM_ADMIN")
    session.accounts[0]["owner_user_id"] = accounts[0].owner_user_id
    session.managed = [old.team_id]
    source = await module.capture_identity_principal(lambda: session, old.actor_id, bound)
    assert source.managed_team_ids == (old.team_id,)
    assert source.source_sha256 == module.source_hash(source)


async def test_current_action_revoke_propagates_without_source_or_network_reads(setup, monkeypatch):
    _bound, session = setup

    async def revoked(*_args):
        raise OrbitError(403, "PERMISSION_DENIED", "当前动作已撤回")

    monkeypatch.setattr(module, "require_business_access", revoked)
    with pytest.raises(OrbitError) as error:
        await capture(setup)
    assert error.value.status == 403 and session.sql == []
    assert session.events[-2:] == ["rollback", "close"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_binding_sha256", "a" * 64),
        ("source_config_id", str(uuid4())),
        ("source_config_revision", 8),
        ("api_version", "v24.0"),
        ("business_id", "999"),
    ],
)
async def test_fact_package_binding_mismatch_fails_closed(setup, monkeypatch, field, value):
    bound, _session = setup
    source = await capture(setup)
    original = await module.observe_identity_principal(
        source, [selected(bound)], transport=Transport()
    )

    async def changed_facts(*_args, **_kwargs):
        return replace(original.facts, **{field: value})

    monkeypatch.setattr(module, "observe_identity_facts", changed_facts)
    with pytest.raises(OrbitError) as error:
        await module.observe_identity_principal(source, [selected(bound)], transport=Transport())
    assert (error.value.status, error.value.code) == (503, "META_PRINCIPAL_OBSERVATION_MISMATCH")


async def test_full_bound_accounts_rechecked_even_if_later_selection_is_one_resource(setup):
    bound, session = setup
    first = bound.source.accounts[0]
    second = replace(first, account_id=str(uuid4()), external_id="002")
    source = replace(
        bound.source, accounts=tuple(sorted([first, second], key=lambda row: row.account_id))
    )
    observed = replace(
        bound.observation,
        accounts=(
            bound.observation.accounts[0],
            replace(bound.observation.accounts[0], external_id="002"),
        ),
    )
    observed = replace(observed, evidence_sha256=stream_digest(observed))
    bound = rebind(replace(bound, observation=observed), source)
    session.accounts.append(
        dict(session.accounts[0]) | {"id": second.account_id, "external_id": "002"}
    )
    session.accounts[1]["revision"] += 1
    with pytest.raises(OrbitError) as error:
        await module.capture_identity_principal(lambda: session, bound.source.actor_id, bound)
    assert (error.value.status, error.value.code) == (409, "META_PRINCIPAL_SOURCE_CHANGED")
