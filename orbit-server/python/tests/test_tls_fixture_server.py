"""真实回环TLS连接回归；无握手预连接和畸形TLS不得阻塞其他请求。"""

import http.client
import importlib
import json
import socket
import ssl
import threading
from pathlib import Path

import pytest


@pytest.mark.parametrize("send_invalid_tls", [False, True])
def test_idle_or_invalid_preconnection_cannot_block_valid_tls(monkeypatch, send_invalid_tls):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    fixture = importlib.import_module("oidc_https_fixture").LocalOidcFixture
    with fixture() as idp:
        accepted = threading.Event()
        dispatch = idp.server.process_request

        def observe_accept(request, address):
            accepted.set()
            dispatch(request, address)

        # 只观察实际监听接收时刻，不替换HTTP、TLS握手或业务响应。
        monkeypatch.setattr(idp.server, "process_request", observe_accept)
        with socket.create_connection(("127.0.0.1", idp.port), timeout=2) as idle:
            assert accepted.wait(2), "监听循环必须先返回未握手连接，再交给工作线程"
            if send_invalid_tls:
                idle.sendall(b"NOT-A-TLS-CLIENT")
                idle.shutdown(socket.SHUT_WR)
            client = http.client.HTTPSConnection(
                "127.0.0.1",
                idp.port,
                timeout=2,
                context=ssl.create_default_context(cadata=idp.ca_pem),
            )
            try:
                client.request("GET", "/.well-known/openid-configuration")
                response = client.getresponse()
                assert response.status == 200
                assert json.loads(response.read())["issuer"] == idp.issuer
            finally:
                client.close()
