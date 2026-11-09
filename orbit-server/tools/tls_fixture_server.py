"""隔离真实TLS夹具：每条连接在线程内握手，闲置预连接不能阻塞监听循环。"""

import ssl
from http.server import ThreadingHTTPServer


class ThreadedTlsFixtureServer(ThreadingHTTPServer):
    def __init__(self, address, handler, context):
        super().__init__(address, handler)
        # SSL监听accept若默认立即握手，会让尚未发ClientHello的浏览器预连接阻塞所有资源。
        self.socket = context.wrap_socket(
            self.socket, server_side=True, do_handshake_on_connect=False
        )

    def process_request_thread(self, request, client_address):
        try:
            # 原转发上游期限15秒不变；握手和请求读也必须有界，且只占自己的工作线程。
            request.settimeout(15)
            request.do_handshake()
        except (OSError, ssl.SSLError):
            self.shutdown_request(request)
            return
        super().process_request_thread(request, client_address)
