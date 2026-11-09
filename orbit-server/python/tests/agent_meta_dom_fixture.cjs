const fs = require('node:fs');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');
const {expression, scenario} = JSON.parse(fs.readFileSync(0, 'utf8'));
function element(text, attrs = {}, tag = 'DIV') {
  return {innerText: text, tagName: tag, getClientRects: () => [1],
    getAttribute: name => attrs[name] ?? null,
    get value() { throw Error('OTP/input value must not be read'); }};
}
let path = '/adsmanager/billing_hub/accounts/details';
let query = '?asset_id=111&payment_account_id=111';
const heading = element('Example Account', {'role':'heading','aria-level':'1'});
const link = element('返回\n\u200b', {href:'/adsmanager/billing_hub/accounts?asset_id=111&payment_account_id=111'} ,'A');
link.parentElement = {children:[link,heading]};
const label = element('货币', {}, 'SPAN');
const value = element('美元 USD');
label.parentElement = {children:[label,value]};
let links = [link], labels = [label], boxes = [], busy = [];
if (scenario === 'campaign') {
  path = '/adsmanager/manage/campaigns'; query = '';
  boxes = [element('Example Account (111)')];
}
if (scenario === 'missing-link') links = [];
if (scenario === 'mismatched-link') link.getAttribute = () => '/adsmanager/billing_hub/accounts?asset_id=222&payment_account_id=222';
if (scenario === 'url-only') {links = [];labels = [];}
if (scenario === 'duplicate-query') query += '&asset_id=111';
if (scenario === 'unobserved-currency') value.innerText = '欧元 EUR';
if (scenario === 'wrong-heading-sibling') link.parentElement = {children:[link,element('Example Account')]};
if (scenario === 'busy') busy = [element('')];
if (scenario === 'challenge') path = '/security/twofactor/reauth/';
const document = {querySelectorAll: selector => {
  if (selector === 'a[role="link"]') return links;
  if (selector === 'span') return labels;
  if (selector === '[role="combobox"][aria-haspopup="listbox"]') return boxes;
  if (selector === '[aria-busy="true"]') return busy;
  return [];
}, get body() { throw Error('body and OTP text must not be read'); }};
const location = {hostname:'adsmanager.facebook.com', pathname:path, href:'https://adsmanager.facebook.com'+path+query};
Promise.resolve(vm.runInNewContext(expression, {document,location,URL,TextEncoder,crypto:webcrypto,
  getComputedStyle: () => ({visibility:'visible',display:'block'})})).then(
    facts => process.stdout.write(JSON.stringify(facts)),
    () => {process.exitCode = 1;}
  );
