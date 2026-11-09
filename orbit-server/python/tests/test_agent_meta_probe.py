import pytest


def test_observed_facebook_home_is_unknown_not_valid():
    from orbit_agent.meta_dom_probe import classify_dom

    result = classify_dom(
        {
            "password": False,
            "challenge": False,
            "account_menu": True,
            "ads_manager": False,
            "currency_marker": False,
        },
        "123",
        "USD",
    )
    assert result["identity_state"] == "UNKNOWN"
    assert result["external_account_id"] is None and result["currency"] is None
    assert result["reason"] == "ACCOUNT_CURRENCY_NOT_OBSERVED"


@pytest.mark.parametrize(
    "facts,state",
    [
        (
            {
                "password": True,
                "challenge": False,
                "account_menu": False,
                "ads_manager": False,
                "currency_marker": False,
            },
            "LOGIN_REQUIRED",
        ),
        (
            {
                "password": False,
                "challenge": True,
                "account_menu": False,
                "ads_manager": False,
                "currency_marker": False,
            },
            "CHALLENGE",
        ),
        (
            {
                "password": False,
                "challenge": False,
                "account_menu": True,
                "ads_manager": True,
                "currency_marker": True,
            },
            "UNKNOWN",
        ),
    ],
)
def test_only_visible_dom_classification_and_no_url_identity(facts, state):
    from orbit_agent.meta_dom_probe import classify_dom

    result = classify_dom(facts, "123", "USD")
    assert result["identity_state"] == state
    assert len(result["evidence_sha256"]) == 64
    assert result["external_account_id"] is None


@pytest.mark.parametrize(
    "host,path,challenge",
    [
        ("adsmanager.facebook.com", "/security/twofactor/reauth/", True),
        ("www.facebook.com", "/security/twofactor/reauth", True),
        ("business.facebook.com", "/security/twofactor/reauth/", True),
        ("adsmanager.facebook.com", "/adsmanager/manage/campaigns", False),
        ("untrusted.example", "/security/twofactor/reauth/", False),
        ("www.facebook.com", "/security/twofactor/reauth/extra", False),
    ],
)
def test_known_twofactor_route_without_reading_otp_or_body(host, path, challenge):
    import json
    import subprocess

    from orbit_agent.meta_dom_probe import DOM_EXPRESSION

    script = """
const vm = require('node:vm');
const document = {
 title: '双重身份验证',
 querySelectorAll: () => [],
 get body() { throw Error('must not read body or OTP text'); }
};
const facts = vm.runInNewContext(EXPRESSION, {
 document, location: LOCATION, getComputedStyle: () => ({})
});
process.stdout.write(JSON.stringify(facts));
""".replace("EXPRESSION", json.dumps(DOM_EXPRESSION)).replace(
        "LOCATION", json.dumps({"hostname": host, "pathname": path})
    )
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    facts = json.loads(result.stdout)
    assert facts["challenge"] is challenge
    assert facts["currency_marker"] is False


def test_known_reauth_page_takes_priority_without_reading_other_tabs():
    from orbit_agent.meta_dom_probe import select_existing_target

    pages = [
        {"type": "page", "targetId": "home", "url": "https://www.facebook.com/"},
        {
            "type": "page",
            "targetId": "challenge",
            "url": "https://adsmanager.facebook.com/security/twofactor/reauth/",
        },
    ]
    assert select_existing_target(pages)["targetId"] == "challenge"
    assert select_existing_target(pages[:1])["targetId"] == "home"
