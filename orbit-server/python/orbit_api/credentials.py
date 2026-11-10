"""配置凭据AES-256-GCM信封；独立主密钥、随机nonce、租户/配置/字段认证绑定。"""

import base64
import binascii
import hashlib
import hmac
import os
import re
import struct

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from orbit_api.errors import OrbitError


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
    if not value or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError
    decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    if _encode(decoded) != value:
        raise ValueError
    return decoded


class CredentialCipher:
    """缺主密钥时可启动并查看脱敏状态，任何密钥读写必须失败，不明文降级。"""

    def __init__(
        self,
        active_key_id: str | None,
        encoded_keys: dict[str, str],
        *,
        forbidden_material: tuple[bytes, ...] = (),
    ):
        self._active = active_key_id
        self._keys: dict[str, bytes] = {}
        try:
            for name, encoded in encoded_keys.items():
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", name):
                    raise ValueError
                key = base64.b64decode(encoded, validate=True)
                if (
                    len(key) != 32
                    or key in forbidden_material
                    or encoded.encode() in forbidden_material
                ):
                    raise ValueError
                self._keys[name] = key
            if self._keys and active_key_id not in self._keys:
                raise ValueError
        except (ValueError, TypeError, binascii.Error):
            raise OrbitError(503, "KEY_CONFIGURATION_INVALID", "服务端独立主密钥配置无效") from None

    def __repr__(self) -> str:
        return "CredentialCipher[REDACTED]"

    @property
    def ready(self) -> bool:
        return self._active in self._keys

    @property
    def active_key_id(self) -> str | None:
        return self._active if self.ready else None

    def application_mac(self, purpose: str, value: bytes, key_id: str | None = None) -> str:
        """只为已注册游标和会话CSRF派生独立用途密钥，不导出主密钥。"""
        if purpose not in {
            "DIRECTORY_CURSOR_V1",
            "DIRECTORY_CSRF_V1",
            "BROWSER_SESSION_CSRF_V1",
            "ACCOUNT_CURSOR_V1",
            "ACCOUNT_SCOPE_CURSOR_V1",
            "ACCOUNT_ASSIGNMENT_OPTIONS_CURSOR_V1",
            "LAUNCH_CURSOR_V1",
            "TEMPLATE_CURSOR_V1",
            "TASK_LIST_CURSOR_V1",
            "TASK_NODE_CURSOR_V1",
            "TASK_EVENT_CHECKPOINT_V1",
            "ACCOUNT_IMPORT_CURSOR_V1",
            "ACCOUNT_DETAILS_CURSOR_V1",
            "ACCOUNT_DETAILS_OWNER_CURSOR_V1",
            "REFERENCE_CURSOR_V1",
            "CHANNEL_CURSOR_V1",
            "MATERIAL_CURSOR_V1",
            "MATERIAL_TAXONOMY_CURSOR_V1",
            "METRIC_PROFILE_CURSOR_V1",
            "METRICS_QUERY_CURSOR_V1",
            "META_SYNC_STATUS_CURSOR_V1",
            "IDENTITY_SUMMARY_SEAL_V1",
            "RULE_CURSOR_V1",
            "RULE_EDITOR_CURSOR_V1",
            "RULE_EDITOR_SCOPE_CURSOR_V1",
            "RULE_SCOPE_OPTIONS_CURSOR_V1",
            "EXECUTION_AGENT_CURSOR_V1",
            "PROFILE_BINDING_CURSOR_V1",
            "AGENT_CAPABILITY_CURSOR_V1",
            "AGENT_PROFILE_CURSOR_V1",
        }:
            raise ValueError("不支持的签名用途")
        key_id = key_id or self.active_key_id
        if key_id not in self._keys:
            raise OrbitError(503, "SIGNING_UNAVAILABLE", "服务端独立签名密钥尚不可用")
        derived = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=("ORBIT_" + purpose).encode("ascii"),
        ).derive(self._keys[key_id])
        return _encode(hmac.new(derived, value, hashlib.sha256).digest())

    def request_digest_internal(self, value: bytes, key_id: str | None) -> str:
        """敏感请求用域隔离派生HMAC；持久化key_id使轮换期间旧幂等请求仍可验证。"""
        if key_id is None:
            # 调用方只允许无REPLACE明文的请求进入该分支。
            return hashlib.sha256(value).hexdigest()
        if key_id not in self._keys:
            raise OrbitError(503, "IDEMPOTENCY_KEY_UNAVAILABLE", "旧幂等摘要密钥版本暂不可用")
        derived = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"ORBIT_CONFIGURATION_IDEMPOTENCY_V1",
        ).derive(self._keys[key_id])
        return hmac.new(derived, value, hashlib.sha256).hexdigest()

    @staticmethod
    def _aad(tenant: str, object_id: str, slot: str) -> bytes:
        values = [value.encode("utf-8") for value in (tenant, object_id, slot)]
        return b"".join(struct.pack(">I", len(value)) + value for value in values)

    def encrypt(self, plaintext: str, tenant: str, object_id: str, slot: str) -> str:
        if not self.ready:
            raise OrbitError(503, "ENCRYPTION_UNAVAILABLE", "服务端尚未配置独立凭据主密钥")
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._keys[self._active]).encrypt(
            nonce, plaintext.encode("utf-8"), self._aad(tenant, object_id, slot)
        )
        return f"v1.{self._active}.{_encode(nonce)}.{_encode(ciphertext)}"

    def decrypt_internal(self, envelope: str, tenant: str, object_id: str, slot: str) -> str:
        """仅供服务端连接器使用；路由、审计和导出不得调用后返回明文。"""
        if not self.ready:
            raise OrbitError(503, "ENCRYPTION_UNAVAILABLE", "服务端尚未配置独立凭据主密钥")
        try:
            if len(envelope) > 65_536:
                raise ValueError
            version, kid, encoded_nonce, encoded_body = envelope.split(".")
            if version != "v1" or kid not in self._keys:
                raise ValueError
            nonce, ciphertext = _decode(encoded_nonce), _decode(encoded_body)
            if len(nonce) != 12 or len(ciphertext) < 16:
                raise ValueError
            return (
                AESGCM(self._keys[kid])
                .decrypt(nonce, ciphertext, self._aad(tenant, object_id, slot))
                .decode("utf-8")
            )
        except Exception:
            raise OrbitError(
                503, "CREDENTIAL_INTEGRITY_FAILED", "凭据完整性或对象归属校验失败"
            ) from None

    def rotate_internal(self, envelope: str, tenant: str, object_id: str, slot: str) -> str:
        """仅生成新信封；事务保存、版本/审计及分批轮换进度由配置服务负责。"""
        return self.encrypt(
            self.decrypt_internal(envelope, tenant, object_id, slot), tenant, object_id, slot
        )
