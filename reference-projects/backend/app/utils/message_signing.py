import hashlib
import hmac
import json

SIGNATURE_KEY_SUFFIX = "mpower"
OP_API_KEY = "REDACTED_REFERENCE_SECRET"


def sign_payload(payload: dict, api_key: str) -> dict:
    """对消息体补齐 api_key 和 sign 字段后返回。"""
    body = {k: v for k, v in payload.items() if k not in ("sign", "api_key")}
    payload_json = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    signing_key = f"{api_key}{SIGNATURE_KEY_SUFFIX}".encode()
    body["api_key"] = api_key
    body["sign"] = hmac.new(signing_key, payload_json.encode(), hashlib.sha256).hexdigest()
    return body
