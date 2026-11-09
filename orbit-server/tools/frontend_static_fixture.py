"""仅供隔离浏览器验收：本机静态构建与固定本机后端代理，不用于部署。"""

import argparse
import http.client
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


def serve(directory):
    directory = Path(directory).resolve(strict=True)
    if not (directory / "index.html").is_file():
        raise ValueError("BUILT_FRONTEND_REQUIRED")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            self.handle_request()

        def do_POST(self):
            self.handle_request()

        def do_PUT(self):
            self.handle_request()

        def do_DELETE(self):
            self.handle_request()

        def do_PATCH(self):
            self.handle_request()

        def handle_request(self):
            if self.headers.get("Host") not in {"localhost:18084", "127.0.0.1:18084"}:
                self.send_error(400)
                return
            parsed = urlsplit(self.path)
            if parsed.scheme or parsed.netloc:
                self.send_error(400)
                return
            prefix = next(
                (p for p in ("/prod-api/", "/dev-api/") if parsed.path.startswith(p)), None
            )
            if prefix:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= 1024 * 1024 or self.headers.get("Transfer-Encoding"):
                    self.send_error(413)
                    return
                excluded = {"host", "connection", "transfer-encoding", "content-length"}
                headers = {k: v for k, v in self.headers.items() if k.lower() not in excluded}
                upstream = http.client.HTTPConnection("127.0.0.1", 18083, timeout=15)
                try:
                    target = parsed.path[len(prefix) - 1 :] + (
                        "?" + parsed.query if parsed.query else ""
                    )
                    upstream.request(self.command, target, self.rfile.read(length), headers)
                    response = upstream.getresponse()
                    body = response.read(16 * 1024 * 1024 + 1)
                    if len(body) > 16 * 1024 * 1024:
                        self.send_error(502)
                        return
                    self.send_response(response.status)
                    for key, value in response.getheaders():
                        if key.lower() not in {"connection", "transfer-encoding", "content-length"}:
                            self.send_header(key, value)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (OSError, http.client.HTTPException):
                    self.send_error(502)
                finally:
                    upstream.close()
                return
            if self.command != "GET":
                self.send_error(405)
                return
            target = (directory / unquote(parsed.path).lstrip("/")).resolve()
            if not target.is_relative_to(directory):
                self.send_error(404)
                return
            if not target.is_file():
                if target.suffix:
                    self.send_error(404)
                    return
                target = directory / "index.html"
            body = target.read_bytes()
            self.send_response(200)
            self.send_header(
                "Content-Type", mimetypes.guess_type(target)[0] or "application/octet-stream"
            )
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    ThreadingHTTPServer(("127.0.0.1", 18084), Handler).serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    serve(parser.parse_args().directory)
