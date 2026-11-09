"""隔离浏览器TLS入口：真实转发应用和IdP，不拦截或模拟认证业务响应。"""

import http.client
import re
import ssl
import threading
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit

from tls_fixture_server import ThreadedTlsFixtureServer


class LocalBrowserGateway:
    """仅监听127.0.0.1:443；端口占用即失败，不停止已有服务或改系统DNS。"""

    def __init__(self, idp):
        self.idp = idp

    def __enter__(self):
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_args):
                pass

            def forward(self):
                response_started = False
                host = self.headers.get("Host", "").partition(":")[0]
                if host not in {"app.fixture.example", "orbit-idp.fixture.example"}:
                    self.send_error(404)
                    return
                if not self.path.startswith("/") or self.headers.get("Transfer-Encoding"):
                    self.send_error(400)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    # 只为固定素材分片路径提升上限，其他测试入口仍保持原有4MiB边界。
                    material_part = host == "app.fixture.example" and re.fullmatch(
                        r"(?:/dev-api)?/api/v1/assets/upload-sessions/[0-9a-fA-F-]{36}/parts/[0-9]{1,5}",
                        urlsplit(self.path).path,
                    )
                    maximum = (8 if material_part else 4) * 1024 * 1024
                    if not 0 <= length <= maximum:
                        raise ValueError
                    body = self.rfile.read(length) if length else None
                    headers = {
                        key: value
                        for key, value in self.headers.items()
                        if key.lower()
                        not in {"host", "connection", "content-length", "transfer-encoding"}
                    }
                    if host == "orbit-idp.fixture.example":
                        connection = http.client.HTTPSConnection(
                            "127.0.0.1",
                            fixture.idp.port,
                            timeout=15,
                            context=ssl.create_default_context(cadata=fixture.idp.ca_pem),
                        )
                        target = self.path
                    else:
                        prefixed_api = self.path.startswith("/dev-api/")
                        api = prefixed_api or self.path.startswith("/api/v1/")
                        connection = http.client.HTTPConnection(
                            "127.0.0.1", 18083 if api else 18084, timeout=15
                        )
                        target = self.path[len("/dev-api") :] if prefixed_api else self.path
                        if not api and urlsplit(target).path in {"/auth/callback", "/invite"}:
                            target = urlsplit(target).path
                    try:
                        connection.request(self.command, target, body=body, headers=headers)
                        response = connection.getresponse()
                        content = response.read()
                        response_started = True
                        self.send_response(response.status)
                        for key, value in response.getheaders():
                            if key.lower() not in {
                                "connection",
                                "transfer-encoding",
                                "content-length",
                            }:
                                self.send_header(key, value)
                        self.send_header("Content-Length", str(len(content)))
                        self.send_header("Connection", "close")
                        self.end_headers()
                        if self.command != "HEAD":
                            self.wfile.write(content)
                    finally:
                        connection.close()
                except (OSError, ValueError, http.client.HTTPException):
                    # 浏览器取消资源请求后连接已关闭，不能再次写入错误响应。
                    if not response_started:
                        try:
                            self.send_response(502)
                            self.send_header("Content-Length", "0")
                            self.send_header("Connection", "close")
                            self.end_headers()
                        except OSError:
                            pass
                finally:
                    self.close_connection = True

            do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = forward

        self.server = ThreadedTlsFixtureServer(
            ("127.0.0.1", 443), Handler, self.idp.server_ssl_context
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
