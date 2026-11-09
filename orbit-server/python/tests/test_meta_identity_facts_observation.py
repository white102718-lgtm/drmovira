"""M3a受控transport纯协议；不证明Meta权限、真实SQL或生产能力发行。"""

import asyncio
import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest

import orbit_api.meta_bound_observation as binding
import orbit_api.meta_identity_facts_observation as module
from orbit_api.directory_tokens import canonical
from orbit_api.errors import OrbitError
from orbit_api.meta_launch_observation import (
    GraphReadResponse,
    MetaAccountObservation,
    MetaIdentityObservation,
    MetaLaunchObservation,
    MetaLaunchReadConfiguration,
    MetaObservationFailure,
    MetaObservationLimits,
)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@pytest.fixture
def bound():
    now = datetime(2026, 11, 9, 8, 0, 0, 123499, tzinfo=UTC)
    tenant, subject, team, account = (str(uuid4()) for _ in range(4))
    config = MetaLaunchReadConfiguration(str(uuid4()), 7, "00123", "v25.0", "fixture-hidden-secret")
    source = binding.MetaSourceSnapshot(
        tenant,
        23,
        subject,
        team,
        "USER",
        9,
        "accounts.sync",
        11,
        now,
        (binding.MetaAccountBinding(account, 5, "001", subject, team),),
        config,
        "",
        binding._ISSUER,
    )
    source = replace(source, binding_sha256=binding.binding_hash(source))
    metadata = dict(
        name="账户",
        currency="USD",
        timezone_name="UTC",
        account_status=1,
        capabilities=["UNKNOWN_FUTURE_VALUE"],
        user_tasks=["MANAGE"],
    )
    resources = tuple(
        MetaIdentityObservation(kind, identifier, "原名")
        for kind, identifier in (
            ("APPLICATION", "007"),
            ("PAGE", "008"),
            ("PIXEL", "009"),
        )
    )
    row = MetaAccountObservation(
        "001", ("owned_ad_accounts",), canonical(metadata).encode(), resources, ()
    )
    observed = MetaLaunchObservation(
        config.source_config_id, 7, "00123", "v25.0", now, now, (row,), "", 6, 1000
    )
    document = dict(
        source_config_id=config.source_config_id,
        source_config_revision=7,
        business_id="00123",
        api_version="v25.0",
        started_at=now.isoformat(),
        observed_at=now.isoformat(),
        accounts=[
            dict(
                external_id="001",
                bm_edges=row.bm_edges,
                metadata=metadata,
                resources=[item.__dict__ for item in resources],
                unknown_fields=(),
            )
        ],
    )
    observed = replace(observed, evidence_sha256=digest(document))
    return binding.BoundMetaObservation(
        source, observed, digest([source.binding_sha256, observed.evidence_sha256])
    )


def selected(bound, kind="PAGE", identifier=None):
    identifier = identifier or {"PAGE": "008", "PIXEL": "009", "APPLICATION": "007"}[kind]
    return module.IdentityFactSelection(bound.source.accounts[0].account_id, kind, identifier)


class Transport:
    def __init__(self, hook=None):
        self.calls, self.hook = [], hook

    async def get(self, target, headers, *, maximum_bytes):
        module.validate_target(target)
        self.calls.append((target, dict(headers), maximum_bytes))
        parsed = urlsplit(target)
        if self.hook:
            result = self.hook(parsed, len(self.calls))
            if result is not None:
                return result
        if parsed.path.endswith("/me"):
            value = {"id": "00042"}
        elif parsed.path.endswith("/assigned_users"):
            value = {
                "data": [{"id": "00042", "business": {"id": "00123"}, "user_type": "SYSTEM_USER"}]
            }
        elif parsed.path.endswith("/008"):
            value = {
                "id": "008",
                "name": "页" * 4096,
                "business": {"id": "00123"},
                "can_post": False,
            }
        elif parsed.path.endswith("/009"):
            value = dict(
                id="009",
                name=None,
                owner_business={"id": "00123"},
                owner_ad_account={"id": "001"},
                is_unavailable=False,
                is_restricted_use=True,
                user_access_expire_time="2026-12-01T00:00:00+0000",
            )
        else:
            value = dict(
                id="007",
                name="应用",
                business={"id": "00123"},
                ios_bundle_id=["com.example.one", "com.example.two"],
                iphone_app_store_id="0123",
                ipad_app_store_id=None,
            )
        return response(value)


def response(value, status=200):
    return GraphReadResponse(status, canonical(value).encode())


async def test_full_whitelist_observations_never_grant_authority(bound):
    transport = Transport()
    result = await module.observe_identity_facts(
        bound, [selected(bound, kind) for kind in module.OBJECT_FIELDS], transport=transport
    )
    assert result.principal_id == "00042"
    assert result.principal_binding == "CONFIG_PRINCIPAL_NOT_BOUND"
    assert result.source_binding_sha256 == bound.binding_sha256
    assert result.source_config_revision == 7 and result.api_version == "v25.0"
    assert result.request_count == 6 and result.response_bytes > 0
    assert result.execution_authorized is False and result.durable is False
    assert result.capability_version is None and result.policy_version is None
    assert result.api_version_compatibility_verified is False
    assert "usable" not in result.__dict__ and "verified" not in result.__dict__
    facts = {row.kind: row for row in result.resources}
    assert json.loads(facts["PAGE"].object_facts_json)["name"] == "页" * 4096
    assert json.loads(facts["PIXEL"].object_facts_json)["name"] is None
    assert "name" in facts["PIXEL"].unknown_fields
    assert json.loads(facts["APPLICATION"].object_facts_json)["ios_bundle_id"] == [
        "com.example.one",
        "com.example.two",
    ]
    assert facts["APPLICATION"].assignment_reason == "NOT_REQUESTED_FOR_APPLICATION"
    assert transport.calls[0][0].endswith("/me?fields=id")
    for target, headers, _maximum in transport.calls:
        assert bound.source.configuration.token not in target
        assert (
            "access_token" not in target
            and "tasks" not in parse_qs(urlsplit(target).query).get("fields", [""])[0]
        )
        assert headers["Authorization"] == "Bearer " + bound.source.configuration.token
    assert bound.source.configuration.token not in repr(result)
    with pytest.raises(FrozenInstanceError):
        result.principal_id = "123"


@pytest.mark.parametrize("mutation", ["issuer", "source", "raw", "combined"])
async def test_tampered_bound_rejected_before_any_network(bound, mutation):
    if mutation == "issuer":
        bound = replace(bound, source=replace(bound.source, _issuer=object()))
    elif mutation == "source":
        bound = replace(bound, source=replace(bound.source, tenant_id=str(uuid4())))
    elif mutation == "raw":
        bound = replace(bound, observation=replace(bound.observation, evidence_sha256="a" * 64))
    else:
        bound = replace(bound, binding_sha256="b" * 64)
    transport = Transport()
    with pytest.raises(OrbitError):
        await module.observe_identity_facts(bound, [selected(bound)], transport=transport)
    assert transport.calls == []


@pytest.mark.parametrize(
    "case", ["foreign", "kind", "missing", "duplicate", "empty", "too_many", "dict"]
)
async def test_explicit_selection_only_from_exact_raw_account_kind_id(bound, case):
    item = selected(bound)
    values = {
        "foreign": [replace(item, account_id=str(uuid4()))],
        "kind": [replace(item, kind="PIXEL")],
        "missing": [replace(item, external_id="888")],
        "duplicate": [item, item],
        "empty": [],
        "too_many": [item] * 501,
        "dict": [item.__dict__],
    }[case]
    transport = Transport()
    with pytest.raises(MetaObservationFailure):
        await module.observe_identity_facts(bound, values, transport=transport)
    assert transport.calls == []


@pytest.mark.parametrize(
    "status,code,expected", [(403, 200, "META_READ_FORBIDDEN"), (400, 100, "META_READ_REJECTED")]
)
async def test_forbidden_or_unsupported_remains_explicit_unverified(bound, status, code, expected):
    transport = Transport(
        lambda _url, _n: response({"error": {"code": code, "message": "do-not-log"}}, status)
    )
    result = await module.observe_identity_facts(bound, [selected(bound)], transport=transport)
    assert result.principal_id is None and result.principal_reason == expected
    row = result.resources[0]
    assert row.object_facts_json is None and row.assignment_facts_json is None
    assert row.object_reason == row.assignment_reason == expected
    assert row.unknown_fields == tuple(module.OBJECT_FIELDS["PAGE"].split(","))
    assert "do-not-log" not in repr(result)


async def test_missing_fields_are_null_not_successful_default_values(bound):
    transport = Transport(
        lambda url, _n: response({"id": "008"}) if url.path.endswith("/008") else None
    )
    result = await module.observe_identity_facts(bound, [selected(bound)], transport=transport)
    row = result.resources[0]
    assert json.loads(row.object_facts_json) == dict(
        id="008", name=None, business=None, can_post=None
    )
    assert row.unknown_fields == ("name", "business", "can_post")


@pytest.mark.parametrize("value", ["008", [], {"id": "wrong"}, {"id": 123}])
async def test_owner_relationship_malformed_never_silently_coerced(bound, value):
    transport = Transport(
        lambda url, _n: (
            response({"id": "008", "business": value}) if url.path.endswith("/008") else None
        )
    )
    with pytest.raises(MetaObservationFailure):
        await module.observe_identity_facts(bound, [selected(bound)], transport=transport)


@pytest.mark.parametrize(
    "field,value,kind",
    [
        ("can_post", 1, "PAGE"),
        ("name", "bad\0", "PAGE"),
        ("name", "\ud800", "PAGE"),
        ("name", "x" * 4097, "PAGE"),
        ("name", "fixture-hidden-secret", "PAGE"),
        ("ios_bundle_id", "com.example.one", "APPLICATION"),
        ("ios_bundle_id", [None], "APPLICATION"),
        ("is_restricted_use", "false", "PIXEL"),
        ("id", "wrong", "PAGE"),
    ],
)
async def test_invalid_types_text_secret_echo_and_response_substitution_fail_closed(
    bound, field, value, kind
):
    item = selected(bound, kind)

    def hook(url, _n):
        if url.path.endswith("/" + item.external_id):
            return response({"id": item.external_id, field: value})
        return None

    with pytest.raises(MetaObservationFailure) as failure:
        await module.observe_identity_facts(bound, [item], transport=Transport(hook))
    assert "fixture-hidden-secret" not in str(failure.value)


async def test_assignments_complete_paging_rebuilds_query_and_drops_next_token(bound):
    def hook(url, _n):
        if url.path.endswith("/assigned_users"):
            params = parse_qs(url.query)
            if "after" not in params:
                return response(
                    dict(
                        data=[dict(id="0001", user_type=None)],
                        paging=dict(
                            next="https://graph.facebook.com/v25.0/008/assigned_users?access_token=NEVERFORWARD",
                            cursors=dict(after="opaque-next"),
                        ),
                    )
                )
            assert params["after"] == ["opaque-next"] and params["business"] == ["00123"]
            assert "NEVERFORWARD" not in url.query
            return response(
                dict(
                    data=[
                        dict(id="0002", business=None, user_type="FUTURE_TYPE", tasks=["ADVERTISE"])
                    ]
                )
            )
        return None

    transport = Transport(hook)
    result = await module.observe_identity_facts(bound, [selected(bound)], transport=transport)
    rows = json.loads(result.resources[0].assignment_facts_json)
    assert [row["id"] for row in rows] == ["0001", "0002"]
    assert rows[0]["user_type"] is None and "tasks" not in rows[1]
    assert result.request_count == 4 and result.execution_authorized is False


@pytest.mark.parametrize(
    "bad", ["host", "path", "no_after", "repeat", "duplicate", "bad_cursor", "invalid_data"]
)
async def test_incomplete_resource_pagination_is_not_partial_success(bound, bad):
    def hook(url, _n):
        if not url.path.endswith("/assigned_users"):
            return None
        if bad == "invalid_data":
            return response({"data": None})
        next_url = "https://graph.facebook.com/v25.0/008/assigned_users"
        if bad == "host":
            next_url = "https://evil.example/v25.0/008/assigned_users"
        elif bad == "path":
            next_url = "https://graph.facebook.com/v25.0/009/assigned_users"
        after = None if bad == "no_after" else "x\0" if bad == "bad_cursor" else "same"
        data = [{"id": "42"}] if bad == "duplicate" else []
        return response(dict(data=data, paging=dict(next=next_url, cursors=dict(after=after))))

    with pytest.raises(MetaObservationFailure):
        await module.observe_identity_facts(bound, [selected(bound)], transport=Transport(hook))


@pytest.mark.parametrize(
    "limits,expected",
    [
        (MetaObservationLimits(max_requests=1), "META_REQUEST_BUDGET_EXCEEDED"),
        (MetaObservationLimits(max_pages=1), "META_PAGE_BUDGET_EXCEEDED"),
        (MetaObservationLimits(max_total_bytes=10), "META_RESPONSE_BUDGET_EXCEEDED"),
        (MetaObservationLimits(max_response_bytes=10), "META_RESPONSE_BUDGET_EXCEEDED"),
        (MetaObservationLimits(max_scope_records=1), "META_RECORD_BUDGET_EXCEEDED"),
    ],
)
async def test_shared_hard_budgets(bound, limits, expected):
    def hook(url, _n):
        if url.path.endswith("/assigned_users"):
            return response(
                dict(
                    data=[{"id": "1"}, {"id": "2"}],
                    paging=dict(
                        next="https://graph.facebook.com/v25.0/008/assigned_users",
                        cursors=dict(after="x"),
                    ),
                )
            )
        return None

    with pytest.raises(MetaObservationFailure) as error:
        await module.observe_identity_facts(
            bound, [selected(bound)], transport=Transport(hook), limits=limits
        )
    assert error.value.code == expected


@pytest.mark.parametrize(
    "target",
    [
        "http://graph.facebook.com/v25.0/me?fields=id",
        "https://graph.facebook.com.evil/v25.0/me?fields=id",
        "https://user@graph.facebook.com/v25.0/me?fields=id",
        "https://graph.facebook.com/v25.0/me?fields=id&access_token=secret",
        "https://graph.facebook.com/v25.0/008?fields=access_token",
        "https://graph.facebook.com/v25.0/me?fields=id&fields=id",
        "https://graph.facebook.com/v25.0/act_1?fields=id",
        "https://graph.facebook.com/v25.0/008/assigned_users?fields=id,tasks&business=1&limit=200",
        "https://graph.facebook.com/v25.0/me?fields=id#fragment",
    ],
)
def test_default_transport_target_whitelist_rejects_injection(target):
    with pytest.raises(MetaObservationFailure):
        module.validate_target(target)


@pytest.mark.parametrize(
    "status,expected",
    [
        (429, "META_RATE_LIMITED"),
        (503, "META_SERVICE_UNAVAILABLE"),
        (302, "META_REDIRECT_REJECTED"),
    ],
)
async def test_transient_or_redirect_never_returns_partial_observation(bound, status, expected):
    with pytest.raises(MetaObservationFailure) as error:
        await module.observe_identity_facts(
            bound, [selected(bound)], transport=Transport(lambda _u, _n: response({}, status))
        )
    assert error.value.code == expected


async def test_transport_exception_never_echoes_url_or_secret(bound):
    class Broken:
        async def get(self, *_args, **_kwargs):
            raise RuntimeError("Authorization: Bearer fixture-hidden-secret")

    with pytest.raises(MetaObservationFailure) as failure:
        await module.observe_identity_facts(bound, [selected(bound)], transport=Broken())
    assert str(failure.value) == "META_READ_UNCERTAIN"


async def test_result_digest_binds_selected_account_and_facts_with_actual_time(bound, monkeypatch):
    now = datetime(2026, 11, 9, 9, 0, 0, 999999, tzinfo=UTC)
    monkeypatch.setattr(module, "utc_now", lambda: now)
    a = await module.observe_identity_facts(bound, [selected(bound)], transport=Transport())
    b = await module.observe_identity_facts(
        bound, [selected(bound, "PIXEL")], transport=Transport()
    )
    assert a.started_at == a.observed_at == now
    assert a.evidence_sha256 != b.evidence_sha256
    assert len(a.evidence_sha256) == 64


async def test_cancel_propagates_no_fake_observation(bound):
    class Cancelled:
        async def get(self, *_args, **_kwargs):
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await module.observe_identity_facts(bound, [selected(bound)], transport=Cancelled())


async def test_digest_independent_complete_document_oracle_and_stable_selection(bound, monkeypatch):
    now = datetime(2026, 11, 9, 9, 0, 0, 123500, tzinfo=UTC)
    monkeypatch.setattr(module, "utc_now", lambda: now)
    items = [selected(bound, "PAGE"), selected(bound, "APPLICATION")]
    result = await module.observe_identity_facts(bound, items, transport=Transport())
    other = await module.observe_identity_facts(bound, list(reversed(items)), transport=Transport())
    expected = {
        "schema_version": 1,
        "source_binding_sha256": bound.binding_sha256,
        "source_config_id": bound.source.configuration.source_config_id,
        "source_config_revision": 7,
        "business_id": "00123",
        "api_version": "v25.0",
        "started_at": now.isoformat(),
        "observed_at": now.isoformat(),
        "principal_id": "00042",
        "principal_reason": None,
        "principal_binding": "CONFIG_PRINCIPAL_NOT_BOUND",
        "resources": [],
    }
    for row in result.resources:
        expected["resources"].append(
            dict(
                account_id=row.account_id,
                kind=row.kind,
                external_id=row.external_id,
                object_facts=json.loads(row.object_facts_json),
                assignments=json.loads(row.assignment_facts_json)
                if row.assignment_facts_json
                else None,
                object_reason=row.object_reason,
                assignment_reason=row.assignment_reason,
                unknown_fields=row.unknown_fields,
            )
        )
    assert result.evidence_sha256 == digest(expected) == other.evidence_sha256
    assert result.resources[0].kind == "APPLICATION"


@pytest.mark.parametrize("maximum,expected", [(100, None), (3, "META_RESPONSE_BUDGET_EXCEEDED")])
async def test_default_transport_get_and_stream_byte_bound_without_real_network(
    monkeypatch, maximum, expected
):
    calls = []

    class Response:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def aiter_stream(self):
            yield b'{"id":'
            yield b'"1"}'

    class Pool:
        def __init__(self, **kwargs):
            assert kwargs["retries"] == 0
            assert kwargs["max_connections"] == 1

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def stream(self, method, target, *, headers, extensions):
            calls.append((method, target, headers))
            assert extensions["timeout"]["read"] == 10
            return Response()

    monkeypatch.setattr(module.httpcore, "AsyncConnectionPool", Pool)
    transport = module.IdentityGraphGetTransport()
    target = "https://graph.facebook.com/v25.0/me?fields=id"
    headers = {"Authorization": "Bearer fixture-memory-only"}
    if expected:
        with pytest.raises(MetaObservationFailure) as failure:
            await transport.get(target, headers, maximum_bytes=maximum)
        assert failure.value.code == expected
    else:
        response = await transport.get(target, headers, maximum_bytes=maximum)
        assert response.body == b'{"id":"1"}' and response.status == 200
    assert calls == [("GET", target, headers)]


async def test_default_transport_rejects_arbitrary_target_before_network(monkeypatch):
    def forbidden_pool(**_kwargs):
        raise AssertionError("网络不应被调用")

    monkeypatch.setattr(module.httpcore, "AsyncConnectionPool", forbidden_pool)
    transport = module.IdentityGraphGetTransport()
    with pytest.raises(MetaObservationFailure) as failure:
        await transport.get("https://evil.example/", {}, maximum_bytes=100)
    assert failure.value.code == "META_TARGET_INVALID"
