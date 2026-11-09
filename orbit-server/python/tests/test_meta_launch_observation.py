"""固定Meta GET采集协议；transport替身不是外部Meta授权或执行验收。"""

import asyncio
import json
import traceback
from dataclasses import FrozenInstanceError, replace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest

from orbit_api.meta_launch_observation import (
    GraphGetTransport,
    GraphReadResponse,
    MetaLaunchObserver,
    MetaLaunchReadConfiguration,
    MetaObservationFailure,
    MetaObservationLimits,
)


def configuration():
    return MetaLaunchReadConfiguration(str(uuid4()), 7, "123", "v23.0", "secret-read-token")


def response(value, status=200):
    return GraphReadResponse(status, json.dumps(value, ensure_ascii=False).encode())


class Transport:
    def __init__(self, override=None):
        self.calls, self.override = [], override

    async def get(self, target, headers, *, maximum_bytes):
        self.calls.append((target, headers, maximum_bytes))
        parsed = urlsplit(target)
        path = parsed.path.split("/", 2)[2]
        if self.override is not None:
            value = self.override(path, parse_qs(parsed.query))
            if value is not None:
                return value
        if path == "123/owned_ad_accounts":
            return response({"data": [{"id": "act_001", "account_id": "001"}]})
        if path == "123/client_ad_accounts":
            return response({"data": []})
        if path == "act_001":
            return response(
                {
                    "id": "act_001",
                    "account_id": "001",
                    "name": "完整账户中文名称",
                    "currency": "USD",
                    "timezone_name": "America/New_York",
                    "account_status": 1,
                    "capabilities": ["VALUE_OBSERVED"],
                    "user_tasks": ["ANALYZE"],
                }
            )
        if path == "act_001/promote_pages":
            return response({"data": [{"id": "009", "name": "真实观察主页"}]})
        if path in {"act_001/adspixels", "act_001/advertisable_applications"}:
            return response({"data": []})
        raise AssertionError("采集器不应访问其他路径")


@pytest.mark.asyncio
async def test_complete_read_observation_has_no_authority_or_policy_and_preserves_text_ids():
    transport, config = Transport(), configuration()
    observed = await MetaLaunchObserver(config, transport=transport).observe(["001"])
    assert observed.complete is True and observed.execution_authorized is False
    assert observed.policy_version is None and observed.workflow_version is None
    assert (
        observed.source_config_id == config.source_config_id
        and observed.source_config_revision == 7
    )
    assert len(observed.evidence_sha256) == 64
    assert observed.request_count == len(transport.calls) == 6
    assert observed.accounts[0].external_id == "001"
    assert observed.accounts[0].resources[0].external_id == "009"
    assert observed.accounts[0].unknown_fields == ()
    for target, headers, limit in transport.calls:
        assert target.startswith("https://graph.facebook.com/v23.0/")
        assert config.token not in target and "access_token" not in target
        assert headers["Authorization"] == "Bearer " + config.token
        assert limit <= 262144
    assert config.token not in repr(config) + repr(observed)
    with pytest.raises(FrozenInstanceError):
        observed.execution_authorized = True


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_config_id", "not-uuid"),
        ("source_config_revision", 0),
        ("source_config_revision", True),
        ("business_id", 123),
        ("business_id", "1/../../me"),
        ("api_version", "https://other"),
        ("token", ""),
        ("token", "token\nheader"),
        ("token", "非ASCII"),
    ],
)
def test_invalid_configuration_fails_without_transport_or_token_repr(field, value):
    with pytest.raises(MetaObservationFailure):
        MetaLaunchObserver(replace(configuration(), **{field: value}), transport=Transport())


@pytest.mark.asyncio
async def test_digest_binds_actual_content_and_configuration_revision_without_hashing_token(
    monkeypatch,
):
    from datetime import UTC, datetime

    import orbit_api.meta_launch_observation as module

    monkeypatch.setattr(module, "utc_now", lambda: datetime(2026, 11, 8, tzinfo=UTC))
    config = configuration()
    original = await MetaLaunchObserver(config, transport=Transport()).observe(["001"])
    rotated = await MetaLaunchObserver(
        replace(config, token="different-secret"), transport=Transport()
    ).observe(["001"])
    changed = await MetaLaunchObserver(
        replace(config, source_config_revision=8), transport=Transport()
    ).observe(["001"])
    assert original.evidence_sha256 == rotated.evidence_sha256
    assert original.evidence_sha256 != changed.evidence_sha256


@pytest.mark.asyncio
async def test_concurrent_observations_do_not_share_budget_or_mutable_resource_cache():
    class YieldingTransport(Transport):
        async def get(self, *args, **kwargs):
            await asyncio.sleep(0)
            return await super().get(*args, **kwargs)

    transport = YieldingTransport()
    observer = MetaLaunchObserver(configuration(), transport=transport)
    first, second = await asyncio.gather(observer.observe(["001"]), observer.observe(["001"]))
    assert first.request_count == second.request_count == 6
    assert len(transport.calls) == 12


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "records,maximum,code",
    [
        ([{"id": 9}], 5000, "META_EXTERNAL_ID_INVALID"),
        ([{"id": "9"}, {"id": "9"}], 5000, "META_OBSERVATION_INCOMPLETE"),
        ([{"id": "9"}, {"id": "10"}], 1, "META_RECORD_BUDGET_EXCEEDED"),
    ],
)
async def test_resource_ids_duplicates_and_total_budget_are_not_silently_normalized(
    records, maximum, code
):
    def override(path, _query):
        if path.endswith("/promote_pages"):
            return response({"data": records})

    with pytest.raises(MetaObservationFailure) as failure:
        await MetaLaunchObserver(
            configuration(),
            transport=Transport(override),
            limits=MetaObservationLimits(max_resources_per_account=maximum),
        ).observe(["001"])
    assert failure.value.code == code


@pytest.mark.asyncio
async def test_external_name_is_not_truncated_to_public_input_limit():
    name = "原始平台名称" * 60

    def override(path, _query):
        if path.endswith("/promote_pages"):
            return response({"data": [{"id": "9", "name": name}]})

    observed = await MetaLaunchObserver(configuration(), transport=Transport(override)).observe(
        ["001"]
    )
    assert observed.accounts[0].resources[0].name == name


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "selection", [[], ["001", "001"], [1], ["act_001"], ["1/owned"], "001", ["1"] * 501]
)
async def test_bad_selection_is_rejected_before_any_request(selection):
    transport = Transport()
    with pytest.raises(MetaObservationFailure):
        await MetaLaunchObserver(configuration(), transport=transport).observe(selection)
    assert transport.calls == []


@pytest.mark.asyncio
async def test_owned_client_union_deduplicates_bm_membership_without_granting_write():
    def override(path, _query):
        if path == "123/client_ad_accounts":
            return response({"data": [{"id": "act_001", "account_id": "001"}]})

    result = await MetaLaunchObserver(configuration(), transport=Transport(override)).observe(
        ["001"]
    )
    assert result.accounts[0].bm_edges == ("client_ad_accounts", "owned_ad_accounts")
    assert result.execution_authorized is False


@pytest.mark.asyncio
async def test_missing_fields_remain_unknown_and_complete_empty_edges_are_not_faked_resources():
    def override(path, _query):
        if path == "act_001":
            return response({"id": "act_001", "account_id": "001"})
        if path.endswith("/promote_pages"):
            return response({"data": [{"id": "009"}]})

    result = await MetaLaunchObserver(configuration(), transport=Transport(override)).observe(
        ["001"]
    )
    account = result.accounts[0]
    assert json.loads(account.metadata_json)["account_status"] is None
    assert account.resources[0].name is None
    assert {"account_status", "capabilities", "PAGE:009:name"} <= set(account.unknown_fields)


@pytest.mark.asyncio
async def test_after_cursor_rebuilds_same_path_and_never_forwards_next_token():
    def override(path, query):
        if path == "act_001/promote_pages":
            if "after" not in query:
                return response(
                    {
                        "data": [{"id": "01", "name": "第一页"}],
                        "paging": {
                            "next": "https://graph.facebook.com/v23.0/act_001/promote_pages?access_token=LEAK",
                            "cursors": {"after": "OPAQUE+/="},
                        },
                    }
                )
            assert query["after"] == ["OPAQUE+/="]
            return response({"data": [{"id": "02", "name": "第二页"}]})

    transport = Transport(override)
    result = await MetaLaunchObserver(configuration(), transport=transport).observe(["001"])
    assert len(result.accounts[0].resources) == 2
    assert all("LEAK" not in target for target, _, _ in transport.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "next_url",
    [
        "https://evil.example/v23.0/act_001/promote_pages",
        "http://graph.facebook.com/v23.0/act_001/promote_pages",
        "https://graph.facebook.com/v23.0/act_002/promote_pages",
        "https://token@graph.facebook.com/v23.0/act_001/promote_pages",
        "https://graph.facebook.com:8080/v23.0/act_001/promote_pages",
        "https://graph.facebook.com/v23.0/act_001/promote_pages#fragment",
    ],
)
async def test_foreign_pagination_is_rejected_without_outbound_follow(next_url):
    def override(path, _query):
        if path.endswith("/promote_pages"):
            return response(
                {"data": [], "paging": {"next": next_url, "cursors": {"after": "next"}}}
            )

    transport = Transport(override)
    with pytest.raises(MetaObservationFailure) as failure:
        await MetaLaunchObserver(configuration(), transport=transport).observe(["001"])
    assert failure.value.code == "META_PAGINATION_INVALID"
    assert len(transport.calls) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("after", [None, "", "bad\ncursor", "非ASCII"])
async def test_next_without_usable_cursor_is_explicitly_incomplete(after):
    def override(path, _query):
        if path.endswith("/promote_pages"):
            return response(
                {
                    "data": [],
                    "paging": {
                        "next": "https://graph.facebook.com/v23.0/" + path,
                        "cursors": {"after": after},
                    },
                }
            )

    with pytest.raises(MetaObservationFailure) as failure:
        await MetaLaunchObserver(configuration(), transport=Transport(override)).observe(["001"])
    assert failure.value.code == "META_OBSERVATION_INCOMPLETE"


@pytest.mark.asyncio
async def test_repeated_cursor_is_incomplete_and_page_budget_is_hard():
    def override(path, _query):
        if path.endswith("/promote_pages"):
            return response(
                {
                    "data": [],
                    "paging": {
                        "next": "https://graph.facebook.com/v23.0/" + path,
                        "cursors": {"after": "repeated"},
                    },
                }
            )

    with pytest.raises(MetaObservationFailure) as failure:
        await MetaLaunchObserver(configuration(), transport=Transport(override)).observe(["001"])
    assert failure.value.code == "META_OBSERVATION_INCOMPLETE"
    with pytest.raises(MetaObservationFailure) as failure:
        await MetaLaunchObserver(
            configuration(),
            transport=Transport(override),
            limits=MetaObservationLimits(max_pages=1),
        ).observe(["001"])
    assert failure.value.code == "META_PAGE_BUDGET_EXCEEDED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "limits,code",
    [
        (MetaObservationLimits(max_requests=2), "META_REQUEST_BUDGET_EXCEEDED"),
        (MetaObservationLimits(max_response_bytes=1), "META_RESPONSE_BUDGET_EXCEEDED"),
        (MetaObservationLimits(max_total_bytes=1), "META_RESPONSE_BUDGET_EXCEEDED"),
    ],
)
async def test_request_and_byte_budgets_refuse_partial_success(limits, code):
    with pytest.raises(MetaObservationFailure) as failure:
        await MetaLaunchObserver(configuration(), transport=Transport(), limits=limits).observe(
            ["001"]
        )
    assert failure.value.code == code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,body,code,retryable",
    [
        (403, {}, "META_READ_FORBIDDEN", False),
        (302, {}, "META_REDIRECT_REJECTED", False),
        (503, {}, "META_SERVICE_UNAVAILABLE", True),
        (429, {}, "META_RATE_LIMITED", True),
        (
            400,
            {"error": {"code": 190, "message": "secret-read-token"}},
            "META_READ_FORBIDDEN",
            False,
        ),
        (400, {"error": {"code": 4, "message": "secret-read-token"}}, "META_RATE_LIMITED", True),
    ],
)
async def test_errors_only_expose_fixed_codes_and_never_echo_graph_body(
    status, body, code, retryable
):
    transport = Transport(lambda _path, _query: response(body, status))
    with pytest.raises(MetaObservationFailure) as failure:
        await MetaLaunchObserver(configuration(), transport=transport).observe(["001"])
    assert (failure.value.code, failure.value.retryable) == (code, retryable)
    assert "secret-read-token" not in "".join(traceback.format_exception(failure.value))


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [b'{"data":[],"data":[]}', b'{"data":NaN}', b"[]", b"not-json"])
async def test_duplicate_or_invalid_json_is_not_a_complete_observation(body):
    with pytest.raises(MetaObservationFailure):
        await MetaLaunchObserver(
            configuration(), transport=Transport(lambda _path, _query: GraphReadResponse(200, body))
        ).observe(["001"])


@pytest.mark.asyncio
async def test_target_not_in_complete_bm_scope_stops_before_account_and_identity_reads():
    transport = Transport()
    with pytest.raises(MetaObservationFailure) as failure:
        await MetaLaunchObserver(configuration(), transport=transport).observe(["999"])
    assert failure.value.code == "META_ACCOUNT_NOT_OBSERVED_IN_BM"
    assert len(transport.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target",
    [
        "https://evil.example/v23.0/act_1",
        "http://graph.facebook.com/v23.0/act_1",
        "https://graph.facebook.com/v23.0/me",
        "https://graph.facebook.com/v23.0/act_1/feed",
    ],
)
async def test_default_transport_rejects_other_host_or_nonwhitelisted_path_before_network(target):
    transport = GraphGetTransport()
    with pytest.raises(MetaObservationFailure) as failure:
        await transport.get(target, {}, maximum_bytes=1)
    assert failure.value.code == "META_TARGET_INVALID"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    ["access_token=secret", "fields=access_token", "fields=id&fields=name", "fields=id&batch=[]"],
)
async def test_default_transport_rejects_token_or_arbitrary_query_before_network(query):
    with pytest.raises(MetaObservationFailure) as failure:
        await GraphGetTransport().get(
            "https://graph.facebook.com/v23.0/act_1?" + query, {}, maximum_bytes=1
        )
    assert failure.value.code == "META_TARGET_INVALID"


@pytest.mark.asyncio
@pytest.mark.parametrize("structured", [False, True])
async def test_transport_exception_context_and_arbitrary_code_cannot_leak_token(structured):
    class BrokenTransport:
        async def get(self, *args, **kwargs):
            if structured:
                raise MetaObservationFailure("secret-read-token")
            raise RuntimeError("secret-read-token")

    with pytest.raises(MetaObservationFailure) as failure:
        await MetaLaunchObserver(configuration(), transport=BrokenTransport()).observe(["001"])
    assert failure.value.code == "META_READ_UNCERTAIN"
    assert "secret-read-token" not in "".join(traceback.format_exception(failure.value))


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["capabilities", "user_tasks"])
@pytest.mark.parametrize("value", ["bad\0text", "bad\ud800text"])
async def test_raw_capability_and_task_text_rejects_nul_or_surrogate_with_fixed_error(field, value):
    def override(path, _query):
        if path == "act_001":
            body = {"id": "act_001", "account_id": "001", field: [value]}
            return GraphReadResponse(200, json.dumps(body, ensure_ascii=True).encode())

    with pytest.raises(MetaObservationFailure) as failure:
        await MetaLaunchObserver(configuration(), transport=Transport(override)).observe(["001"])
    assert (failure.value.code, failure.value.retryable) == ("META_OBSERVATION_INVALID", False)
