"""新增真实工具的解析/断言协议纯测；不冒充HTTPS IdP或Cookie实测。"""

import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from task_event_cookie_checks import consume_revocation, issued_pair  # noqa: E402


def test_cookie_parser_keeps_only_required_pair_in_memory():
    response = httpx.Response(
        200,
        headers=[
            ("set-cookie", "adpilot_session=fixture-only; Secure; HttpOnly; SameSite=lax; Path=/")
        ],
    )
    assert issued_pair(response, "bound-fixture") == (
        "adpilot_session=fixture-only; __Host-orbit_browser=bound-fixture"
    )


@pytest.mark.parametrize(
    "header",
    [
        "unrelated=value; Secure; HttpOnly; SameSite=lax; Path=/",
        "adpilot_session=fixture-only; HttpOnly; SameSite=lax; Path=/",
        "adpilot_session=fixture-only; Secure; HttpOnly; SameSite=lax; Path=/; Domain=example.org",
    ],
)
def test_cookie_parser_rejects_missing_or_unsafe_session_without_echoing_value(header):
    with pytest.raises(AssertionError) as failure:
        issued_pair(httpx.Response(200, headers={"set-cookie": header}), "binding")
    assert "fixture-only" not in str(failure.value)


def test_revocation_observer_reports_only_elapsed_seconds(monkeypatch):
    import task_event_cookie_checks as checks

    monkeypatch.setattr(checks.time, "monotonic", lambda: 10.25)
    assert (
        consume_revocation(
            iter(["", "event: SCOPE_REVOKED", 'data: {"code":"SCOPE_REVOKED"}', ""]), 10.0
        )
        == 0.25
    )


@pytest.mark.parametrize(
    "lines",
    [
        ["id: forbidden", "data: {}"],
        ["event: SCOPE_REVOKED", 'data: {"code":"SCOPE_REVOKED","sequence":1}'],
        ["event: SCOPE_REVOKED", "id: forbidden", 'data: {"code":"SCOPE_REVOKED"}'],
    ],
)
def test_revocation_parser_rejects_old_business_data_or_global_sequence(lines):
    with pytest.raises(AssertionError):
        consume_revocation(iter(lines), 0.0)


def test_revocation_two_seconds_bound_is_not_weakened(monkeypatch):
    import task_event_cookie_checks as checks

    monkeypatch.setattr(checks.time, "monotonic", lambda: 12.0)
    with pytest.raises(AssertionError):
        consume_revocation(iter(["event: SCOPE_REVOKED", 'data: {"code":"SCOPE_REVOKED"}']), 10.0)
