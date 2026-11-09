from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Mapping

SIGNATURE_KEY_SUFFIX = "mpower"


def normalize_api_key(api_key: str) -> str:
    """规范化调用方传入的 api_key，用于签名和最终消息输出。"""

    normalized = str(api_key or "").strip()
    if not normalized:
        raise ValueError("api_key is required when publish is true")
    return normalized


def build_signing_key(api_key: str) -> str:
    """基于调用方传入的 api_key 构造签名 key。"""

    normalized_api_key = normalize_api_key(api_key)
    return f"{normalized_api_key}{SIGNATURE_KEY_SUFFIX}"


def build_signing_payload_json(payload: Mapping[str, Any]) -> str:
    """将待签名消息序列化为按字段名字母排序的规范化 JSON。"""

    payload_for_signing = dict(payload)
    payload_for_signing.pop("sign", None)
    payload_for_signing.pop("api_key", None)
    return json.dumps(
        payload_for_signing,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def build_signature(payload: Mapping[str, Any], api_key: str) -> str:
    """对规范化 JSON 消息生成 HMAC-SHA256 签名。"""

    normalized_api_key = normalize_api_key(api_key)
    payload_json = build_signing_payload_json(payload)
    return hmac.new(
        build_signing_key(normalized_api_key).encode("utf-8"),
        payload_json.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def build_signed_payload(payload: Mapping[str, Any], api_key: str) -> dict[str, Any]:
    """在发送前为消息补齐 api_key 和 sign 字段。"""

    normalized_api_key = normalize_api_key(api_key)
    signed_payload = json.loads(build_signing_payload_json(payload))
    signed_payload["api_key"] = normalized_api_key
    signed_payload["sign"] = build_signature(signed_payload, normalized_api_key)
    return signed_payload


def verify_signature(payload: Mapping[str, Any], api_key: str) -> bool:
    """验证消息签名，返回 True 表示验签通过，False 表示验签失败。"""
    received_sign = payload.get("sign")
    if not received_sign:
        return False
    expected_sign = build_signature(payload, api_key)
    return hmac.compare_digest(received_sign, expected_sign)


__all__ = [
    "SIGNATURE_KEY_SUFFIX",
    "build_signature",
    "build_signing_payload_json",
    "build_signed_payload",
    "build_signing_key",
    "normalize_api_key",
    "verify_signature",
]
