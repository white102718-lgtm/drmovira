"""只使用虚构账户；跨页关联必须包括账户DOM和名称摘要，不接受URL裸拼。"""

from hashlib import sha256

import pytest


def page(*, selectors=(), billing=None, **overrides):
    return {
        "password": False,
        "challenge": False,
        "busy": False,
        "selectors": list(selectors),
        "billing": billing,
        "incomplete": False,
    } | overrides


def identity(account="111", name="Example Account", currency=None):
    value = {"account_id": account, "name_sha256": sha256(name.encode()).hexdigest()}
    return value if currency is None else value | {"currency": currency}


def test_matching_rendered_selector_and_billing_evidence_can_be_valid():
    from orbit_agent.meta_dom_v2 import classify_pages

    result = classify_pages(
        [page(), page(selectors=[identity()]), page(billing=identity(currency="USD"))], "111", "USD"
    )
    assert result["identity_state"] == "VALID"
    assert result["external_account_id"] == "111" and result["currency"] == "USD"


@pytest.mark.parametrize(
    "pages,state",
    [
        ([page(billing=identity(currency="USD"))], "UNKNOWN"),
        ([page(selectors=[identity()])], "UNKNOWN"),
        ([page(selectors=[identity("222")])], "IDENTITY_MISMATCH"),
        (
            [page(selectors=[identity()]), page(billing=identity(name="Other", currency="USD"))],
            "IDENTITY_MISMATCH",
        ),
        (
            [page(selectors=[identity()]), page(billing=identity(currency="USD"), busy=True)],
            "UNKNOWN",
        ),
        (
            [page(selectors=[identity()]), page(billing=identity(currency="USD"), incomplete=True)],
            "UNKNOWN",
        ),
        (
            [page(selectors=[identity(), identity("222")]), page(billing=identity(currency="USD"))],
            "IDENTITY_MISMATCH",
        ),
        ([page(challenge=True), page(selectors=[identity()])], "CHALLENGE"),
        ([page(password=True)], "LOGIN_REQUIRED"),
    ],
)
def test_missing_conflicting_or_busy_evidence_never_valid(pages, state):
    from orbit_agent.meta_dom_v2 import classify_pages

    assert classify_pages(pages, "111", "USD")["identity_state"] == state


def test_expected_currency_is_not_copied_into_observed_evidence():
    from orbit_agent.meta_dom_v2 import classify_pages

    pages = [page(selectors=[identity()]), page(billing=identity(currency="USD"))]
    mismatch = classify_pages(pages, "111", "EUR")
    assert mismatch["identity_state"] == "IDENTITY_MISMATCH"
    assert mismatch["currency"] == "USD"
    assert classify_pages(pages, None, None)["identity_state"] == "UNKNOWN"


def test_reject_arbitrary_fields_and_raw_account_names():
    from orbit_agent.adspower_status import ProbeError
    from orbit_agent.meta_dom_v2 import classify_pages

    with pytest.raises(ProbeError):
        classify_pages([page(selectors=[identity() | {"name": "Private Name"}])], "111", "USD")


@pytest.mark.parametrize(
    "scenario,has_billing",
    [
        ("billing", True),
        ("missing-link", False),
        ("mismatched-link", False),
        ("url-only", False),
        ("duplicate-query", False),
        ("unobserved-currency", False),
        ("wrong-heading-sibling", False),
    ],
)
def test_actual_js_requires_complete_observed_billing_structure(scenario, has_billing):
    import json
    import subprocess
    from pathlib import Path

    from orbit_agent.meta_dom_v2 import DOM_EXPRESSION_V2

    result = subprocess.run(
        ["node", str(Path(__file__).with_name("agent_meta_dom_fixture.cjs"))],
        input=json.dumps({"expression": DOM_EXPRESSION_V2, "scenario": scenario}),
        text=True,
        capture_output=True,
        check=True,
    )
    facts = json.loads(result.stdout)
    assert (facts["billing"] is not None) is has_billing
    assert "Example Account" not in result.stdout and "https://" not in result.stdout
    if has_billing:
        assert facts["billing"] == identity(name="Example Account", currency="USD")
    else:
        assert facts["incomplete"] is True


def test_actual_js_account_selector_matches_billing_hash_without_exporting_name():
    import json
    import subprocess
    from pathlib import Path

    from orbit_agent.meta_dom_v2 import DOM_EXPRESSION_V2

    result = subprocess.run(
        ["node", str(Path(__file__).with_name("agent_meta_dom_fixture.cjs"))],
        input=json.dumps({"expression": DOM_EXPRESSION_V2, "scenario": "campaign"}),
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(result.stdout)["selectors"] == [identity(name="Example Account")]
    assert "Example Account" not in result.stdout


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", [None, "facts", "target"])
async def test_readonly_cdp_requires_two_stable_snapshots_and_target_set(monkeypatch, mutation):
    import json

    import websockets.asyncio.client

    from orbit_agent.adspower_status import ProbeError
    from orbit_agent.meta_dom_probe import observe_existing_pages

    class Bridge:
        def __init__(self):
            self.request = None
            self.methods = []
            self.evaluations = 0
            self.target_reads = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def send(self, raw):
            self.request = json.loads(raw)
            self.methods.append(self.request["method"])

        async def recv(self):
            request = self.request
            method = request["method"]
            result = {}
            if method == "Target.getTargets":
                self.target_reads += 1
                url = "https://adsmanager.facebook.com/adsmanager/manage/campaigns"
                if mutation == "target" and self.target_reads > 1:
                    url += "?changed=1"
                result = {"targetInfos": [{"type": "page", "targetId": "p", "url": url}]}
            elif method == "Target.attachToTarget":
                result = {"sessionId": "existing-session"}
            elif method == "Runtime.evaluate":
                self.evaluations += 1
                facts = page(selectors=[identity()])
                if mutation == "facts" and self.evaluations > 1:
                    facts["busy"] = True
                result = {"result": {"value": facts}}
            return json.dumps({"id": request["id"], "result": result})

    bridge = Bridge()
    monkeypatch.setattr(websockets.asyncio.client, "connect", lambda *args, **kwargs: bridge)
    endpoint = "ws://127.0.0.1:9222/devtools/browser/example"
    if mutation:
        with pytest.raises(ProbeError):
            await observe_existing_pages(endpoint)
    else:
        assert await observe_existing_pages(endpoint) == [page(selectors=[identity()])]
    assert bridge.evaluations == 2
    assert set(bridge.methods) == {
        "Target.getTargets",
        "Target.attachToTarget",
        "Runtime.evaluate",
        "Target.detachFromTarget",
    }
