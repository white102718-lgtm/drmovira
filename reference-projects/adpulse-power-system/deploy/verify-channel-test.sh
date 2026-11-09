#!/usr/bin/env bash
set -Eeuo pipefail

base_url="${BASE_URL:-http://127.0.0.1:5555/main}"
session_id="channel-deploy-smoke-$(date +%s)-$$"
user_id="${TEST_USER_ID:-1}"
redis_password="$(docker exec adpulse-system-redis sh -lc 'printf %s "$REDIS_PASSWORD"')"
jwt_secret="$(docker exec adpulse-main-server sh -lc 'printf %s "$JWT_SECRET"')"
session_key="adpulse:session:${session_id}"
user_sessions_key="adpulse:user-sessions:${user_id}"
created_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
session_json="{\"sessionId\":\"${session_id}\",\"userId\":${user_id},\"displayName\":\"渠道发布检查\",\"loginIp\":\"127.0.0.1\",\"permissions\":[],\"createdAt\":\"${created_at}\"}"

cleanup() {
  docker exec adpulse-system-redis redis-cli -a "$redis_password" DEL "$session_key" >/dev/null
  docker exec adpulse-system-redis redis-cli -a "$redis_password" SREM "$user_sessions_key" "$session_id" >/dev/null
}
trap cleanup EXIT

docker exec adpulse-system-redis redis-cli -a "$redis_password" SETEX "$session_key" 600 "$session_json" >/dev/null
docker exec adpulse-system-redis redis-cli -a "$redis_password" SADD "$user_sessions_key" "$session_id" >/dev/null
docker exec adpulse-system-redis redis-cli -a "$redis_password" EXPIRE "$user_sessions_key" 600 >/dev/null

export JWT_SECRET="REDACTED_REFERENCE_SECRET" SESSION_ID="$session_id" USER_ID="$user_id"
token="$(python3 - <<'PY'
import base64
import hashlib
import hmac
import json
import os
import time

def encode(value):
    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

now = int(time.time())
header = encode({"alg": "HS256", "typ": "JWT"})
payload = encode({
    "iss": "adpulse-system-server",
    "sub": os.environ["USER_ID"],
    "sid": os.environ["SESSION_ID"],
    "iat": now,
    "exp": now + 600,
})
content = f"{header}.{payload}"
signature = hmac.new(
    os.environ["JWT_SECRET"].encode(), content.encode(), hashlib.sha256
).digest()
print(f"{content}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}")
PY
)"

channels="$(curl --fail --silent --show-error --max-time 10 \
  -H "Authorization: Bearer $token" \
  "$base_url/channels?page=1&pageSize=10&status=1&belongTeam=Mpower")"
channel_id="$(printf '%s' "$channels" | python3 -c '
import json, sys
body=json.load(sys.stdin)
assert body["code"] == 200, body
items = body["data"]["items"]
assert items, body
demo_codes = {"METASG", "METAEU", "METAUL", "TTASIA"}
active_demo_codes = sorted(
    item["channelCode"] for item in items if item.get("channelCode") in demo_codes
)
assert not active_demo_codes, {
    "message": "共享测试环境仍返回演示渠道",
    "activeDemoCodes": active_demo_codes,
}
print(items[0]["id"])
')"

detail="$(curl --fail --silent --show-error --max-time 10 \
  -H "Authorization: Bearer $token" "$base_url/channels/$channel_id")"
accounts="$(curl --fail --silent --show-error --max-time 10 \
  -H "Authorization: Bearer $token" \
  -H 'Content-Type: application/json' \
  -d "{\"channelId\":$channel_id,\"page\":1,\"pageSize\":10}" \
  "$base_url/channel-accounts/search")"
channels="$(curl --fail --silent --show-error --max-time 10 \
  -H "Authorization: Bearer $token" \
  "$base_url/channels?page=1&pageSize=1000&status=1")"

python3 - "$detail" "$accounts" "$channels" <<'PY'
import json
import sys

detail, accounts, channels = (json.loads(value) for value in sys.argv[1:])
assert detail["code"] == 200, detail
assert accounts["code"] == 200, accounts
assert channels["code"] == 200, channels
print(json.dumps({
    "channelId": detail["data"]["id"],
    "channelName": detail["data"]["channelName"],
    "associatedAccounts": accounts["data"]["total"],
    "activeChannels": channels["data"]["total"],
}, ensure_ascii=False))
PY
