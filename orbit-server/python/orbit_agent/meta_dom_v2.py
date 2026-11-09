"""受限中文美元账单DOM证据；账户选择框与账单身份链同时成立才可验证。"""

import hashlib
import json
import re

from orbit_agent.adspower_status import ProbeError

ADAPTER = "ADSPOWER_META_DOM_V2"


def _fail():
    raise ProbeError("IDENTITY_PROBE_FAILED")


def _identity(value, *, billing=False):
    keys = {"account_id", "name_sha256"} | ({"currency"} if billing else set())
    if type(value) is not dict or set(value) != keys:
        _fail()
    if (
        type(value["account_id"]) is not str
        or re.fullmatch(r"[0-9]{1,64}", value["account_id"]) is None
        or type(value["name_sha256"]) is not str
        or re.fullmatch(r"[a-f0-9]{64}", value["name_sha256"]) is None
        or (billing and value["currency"] != "USD")
    ):
        _fail()


def classify_pages(pages, expected_account_id, expected_currency):
    """只接收固定事实和名称摘要；不接收URL、账户名、DOM正文或凭据。"""
    keys = {"password", "challenge", "busy", "selectors", "billing", "incomplete"}
    if type(pages) is not list or not 1 <= len(pages) <= 20:
        _fail()
    for page in pages:
        if (
            type(page) is not dict
            or set(page) != keys
            or any(
                type(page[key]) is not bool
                for key in ("password", "challenge", "busy", "incomplete")
            )
            or type(page["selectors"]) is not list
            or len(page["selectors"]) > 10
        ):
            _fail()
        for value in page["selectors"]:
            _identity(value)
        if page["billing"] is not None:
            _identity(page["billing"], billing=True)
    state, reason = "UNKNOWN", "ACCOUNT_CURRENCY_NOT_OBSERVED"
    actual, currency = None, None
    selectors = [value for page in pages for value in page["selectors"]]
    bills = [page["billing"] for page in pages if page["billing"] is not None]
    identities = selectors + bills
    if any(page["challenge"] for page in pages):
        state, reason = "CHALLENGE", "VISIBLE_CHALLENGE"
    elif any(page["password"] for page in pages):
        state, reason = "LOGIN_REQUIRED", "VISIBLE_PASSWORD_INPUT"
    elif any(page["busy"] or page["incomplete"] for page in pages):
        reason = "DOM_EVIDENCE_INCOMPLETE"
    elif expected_account_id is None or expected_currency is None:
        reason = "EXPECTED_IDENTITY_NOT_CONFIGURED"
    elif any(value["account_id"] != expected_account_id for value in identities):
        state, reason = "IDENTITY_MISMATCH", "OBSERVED_ACCOUNT_MISMATCH"
        distinct = {value["account_id"] for value in identities}
        actual = next(iter(distinct)) if len(distinct) == 1 else None
    elif len({value["name_sha256"] for value in identities}) > 1:
        state, reason = "IDENTITY_MISMATCH", "OBSERVED_ACCOUNT_NAME_CONFLICT"
        actual = identities[0]["account_id"]
    elif any(value["currency"] != expected_currency for value in bills):
        state, reason = "IDENTITY_MISMATCH", "OBSERVED_CURRENCY_MISMATCH"
        actual, currency = bills[0]["account_id"], bills[0]["currency"]
    elif selectors and bills:
        state, reason = "VALID", "MATCHED_RENDERED_ACCOUNT_AND_BILLING"
        actual, currency = bills[0]["account_id"], bills[0]["currency"]
    evidence = {"adapter": ADAPTER, "pages": pages, "state": state, "reason": reason}
    return {
        "identity_state": state,
        "external_account_id": actual,
        "currency": currency,
        "reason": reason,
        "evidence_sha256": hashlib.sha256(
            json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


DOM_EXPRESSION_V2 = r"""(async () => {
 const visible = e => !!e && e.getClientRects().length > 0 &&
   getComputedStyle(e).visibility !== 'hidden' && getComputedStyle(e).display !== 'none';
 const all = selector => Array.from(document.querySelectorAll(selector)).filter(visible);
 const text = e => (e.innerText || '').normalize('NFC').trim();
 const digest = async name => Array.from(new Uint8Array(await crypto.subtle.digest(
   'SHA-256', new TextEncoder().encode(name)))).map(x => x.toString(16).padStart(2,'0')).join('');
 const trusted = ['www.facebook.com','business.facebook.com','adsmanager.facebook.com']
   .includes(location.hostname);
 const facts = {
   password: all('input[type="password"]').length > 0,
   challenge: (trusted && /^\/security\/twofactor\/reauth\/?$/.test(location.pathname)) ||
     all('input[name="approvals_code"],input[name="captcha_response"],' +
       'iframe[src*="captcha"]').length > 0,
   busy: all('[aria-busy="true"]').length > 0,
   selectors: [], billing: null, incomplete: false
 };
 if (facts.challenge || facts.password || location.hostname !== 'adsmanager.facebook.com') {
   return facts;
 }
 if (location.pathname === '/adsmanager/manage/campaigns') {
   const boxes = all('[role="combobox"][aria-haspopup="listbox"]');
   for (const box of boxes) {
     const match = text(box).match(/^(.+) \(([0-9]{1,64})\)$/u);
     if (match && match[1].trim().length > 0 && match[1].length <= 512) {
       facts.selectors.push({account_id: match[2], name_sha256: await digest(match[1].trim())});
     }
   }
   if (facts.selectors.length === 0 || facts.selectors.length > 10) {
     facts.selectors = []; facts.incomplete = true;
   }
 }
 if (location.pathname === '/adsmanager/billing_hub/accounts/details') {
   facts.incomplete = true;
   const links = all('a[role="link"]').filter(e =>
     text(e).replace(/[\u200B-\u200D\uFEFF]/g, '').trim() === '返回');
   const labels = all('span').filter(e => text(e) === '货币');
   if (links.length !== 1 || labels.length !== 1) return facts;
   const link = links[0], children = Array.from(link.parentElement?.children || []);
   if (children.length !== 2 || children[0] !== link) return facts;
   const heading = children[1];
   if (!visible(heading) || heading.getAttribute('role') !== 'heading' ||
       heading.getAttribute('aria-level') !== '1') return facts;
   const name = text(heading);
   if (!name || name.length > 512) return facts;
   const field = Array.from(labels[0].parentElement?.children || []);
   if (field.length !== 2 || field[0] !== labels[0] || field[0].tagName !== 'SPAN' ||
       field[1].tagName !== 'DIV' || !visible(field[1]) || text(field[1]) !== '美元 USD') {
     return facts;
   }
   const current = new URL(location.href), back = new URL(link.getAttribute('href'), location.href);
   if (back.origin !== current.origin || back.pathname !== '/adsmanager/billing_hub/accounts') {
     return facts;
   }
   const ids = [current,back].flatMap(url => ['asset_id','payment_account_id'].map(key => {
     const values = url.searchParams.getAll(key);
     return values.length === 1 && /^[0-9]{1,64}$/.test(values[0]) ? values[0] : null;
   }));
   if (ids.some(id => id === null || id !== ids[0])) return facts;
   facts.billing = {account_id: ids[0], name_sha256: await digest(name), currency: 'USD'};
   facts.incomplete = false;
 }
 return facts;
})()"""
