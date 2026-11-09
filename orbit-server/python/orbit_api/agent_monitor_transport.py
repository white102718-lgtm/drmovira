"""只从真实TLS连接获取设备证书；不接受代理头、Cookie或Bearer替代mTLS。"""

import ssl
from dataclasses import dataclass

from uvicorn.protocols.http.h11_impl import H11Protocol

from orbit_api.errors import OrbitError


@dataclass(frozen=True, repr=False)
class DevicePeer:
    certificate_der: bytes


class PeerCertificateH11Protocol(H11Protocol):
    def connection_made(self, transport):
        super().connection_made(transport)
        ssl_object = transport.get_extra_info("ssl_object")
        der = None
        if ssl_object is not None and ssl_object.context.verify_mode == ssl.CERT_REQUIRED:
            der = ssl_object.getpeercert(binary_form=True)
        peer = DevicePeer(der) if der else None
        app = self.app

        async def authenticated(scope, receive, send):
            # 每条HTTP请求均由本连接transport覆盖；浏览器/反向代理传同名header无效。
            scope["orbit.device_peer"] = peer
            await app(scope, receive, send)

        self.app = authenticated


def peer_certificate(scope):
    peer = scope.get("orbit.device_peer")
    if type(peer) is not DevicePeer or not peer.certificate_der or scope.get("scheme") != "https":
        raise OrbitError(401, "DEVICE_CERTIFICATE_REQUIRED", "需要受信任设备双向TLS连接")
    return peer.certificate_der
