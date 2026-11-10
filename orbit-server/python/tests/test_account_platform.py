"""真实本机TLS的只读Graph协议专项；不请求真实Meta或证明生产权限。"""

import pytest
from tools.account_platform_checks import local_graph

from orbit_api.account_platform import (
    AccountReadFailure,
)


@pytest.fixture
def graph(tmp_path):
    with local_graph(tmp_path) as value:
        yield value


async def test_actual_tls_membership_then_metadata_only_get_and_token_not_url(graph):
    await graph.reader.prepare(["001"])
    value = await graph.reader.fetch_metadata("001")
    assert value["external_id"] == "001" and value["currency"] == "USD"
    assert value["timezone_id"] == "America/New_York"
    assert "balance" not in value and "spend" not in value
    assert len(graph.requests) == 7  # 基础读取加五个独立可选字段，拒绝不阻断其他字段。
    for method, path, headers in graph.requests:
        assert method == "GET" and "fixture-secret-token" not in path and "access_token" not in path
        assert headers["Authorization"] == "Bearer fixture-secret-token"


async def test_client_bm_membership_is_explicitly_read_not_guessed_from_owner(graph):
    graph.mode = "client"
    await graph.reader.prepare(["001"])
    await graph.reader.fetch_metadata("001")
    assert any("/client_ad_accounts?" in path for _, path, _ in graph.requests)


async def test_missing_membership_cannot_probe_account_even_if_token_might_read_it(graph):
    graph.mode = "missing"
    await graph.reader.prepare(["001"])
    with pytest.raises(AccountReadFailure) as error:
        await graph.reader.fetch_metadata("001")
    assert error.value.code == "ACCOUNT_PLATFORM_FORBIDDEN"
    assert len(graph.requests) == 2 and all(
        "/act_001?" not in path for _, path, _ in graph.requests
    )


async def test_paging_rebuilds_fixed_host_query_never_follows_next_url(graph):
    graph.mode = "paged"
    await graph.reader.prepare(["001"])
    assert len(graph.requests) == 2
    assert "after=cursor-two" in graph.requests[1][1]
    assert all("evil" not in path and "access_token" not in path for _, path, _ in graph.requests)


@pytest.mark.parametrize(
    "mode,code,retryable",
    [
        ("redirect", "ACCOUNT_PLATFORM_REDIRECT_REJECTED", False),
        ("rate", "ACCOUNT_PLATFORM_RATE_LIMITED", True),
        ("forbidden", "ACCOUNT_PLATFORM_FORBIDDEN", False),
        ("graph-error", "ACCOUNT_PLATFORM_FORBIDDEN", False),
        ("graph-rate", "ACCOUNT_PLATFORM_RATE_LIMITED", True),
        ("graph-transient", "ACCOUNT_PLATFORM_UNAVAILABLE", True),
        ("server-error", "ACCOUNT_PLATFORM_UNAVAILABLE", True),
        ("disconnect", "ACCOUNT_PLATFORM_READ_UNCERTAIN", True),
        ("duplicate-json", "ACCOUNT_PLATFORM_RESPONSE_INVALID", False),
    ],
)
async def test_actual_tls_failures_never_retry_inline_or_expose_raw_response(
    graph, mode, code, retryable
):
    graph.mode = mode
    with pytest.raises(AccountReadFailure) as error:
        await graph.reader.prepare(["001"])
    assert error.value.code == code and error.value.retryable == retryable
    assert len(graph.requests) == 1 and "fixture-secret-token" not in str(error.value)


@pytest.mark.parametrize("mode", ["wrong-id", "missing-field", "invalid-name"])
async def test_metadata_identity_or_missing_timezone_never_becomes_success(graph, mode):
    await graph.reader.prepare(["001"])
    graph.mode = mode
    with pytest.raises(AccountReadFailure) as error:
        await graph.reader.fetch_metadata("001")
    assert error.value.code == "ACCOUNT_METADATA_INVALID"


async def test_success_shaped_http400_metadata_is_still_rejected(graph):
    await graph.reader.prepare(["001"])
    graph.mode = "bad-request-metadata"
    with pytest.raises(AccountReadFailure) as error:
        await graph.reader.fetch_metadata("001")
    assert error.value.code == "ACCOUNT_PLATFORM_REQUEST_REJECTED"


async def test_platform_original_name_is_not_truncated_to_import_row_display_limit(graph):
    await graph.reader.prepare(["001"])
    graph.mode = "long-name"
    value = await graph.reader.fetch_metadata("001")
    assert value["name"] == "名" * 10000


async def test_failed_new_precheck_cannot_reuse_prior_authorized_membership(graph):
    await graph.reader.prepare(["001"])
    graph.mode = "forbidden"
    with pytest.raises(AccountReadFailure):
        await graph.reader.prepare(["001"])
    with pytest.raises(AccountReadFailure) as error:
        await graph.reader.fetch_metadata("001")
    assert error.value.code == "ACCOUNT_SCOPE_PRECHECK_REQUIRED"


async def test_incomplete_paging_cannot_claim_absent_account_is_authorized(graph):
    graph.mode = "scope-incomplete"
    with pytest.raises(AccountReadFailure) as error:
        await graph.reader.prepare(["001"])
    assert error.value.code == "ACCOUNT_PLATFORM_SCOPE_INVALID"
    assert len(graph.requests) == 2 and graph.reader.authorized is None


async def test_live_local_preflight_rejection_sends_no_external_request(graph):
    async def rejected():
        raise AccountReadFailure("ACCOUNT_IMPORT_AUTHORIZATION_CHANGED")

    graph.reader.preflight = rejected
    with pytest.raises(AccountReadFailure) as error:
        await graph.reader.prepare(["001"])
    assert error.value.code == "ACCOUNT_IMPORT_AUTHORIZATION_CHANGED"
    assert graph.requests == []
