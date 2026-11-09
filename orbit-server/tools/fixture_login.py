"""正向独立夹具登录：遇原限流只等DB15窗口自然过期；429协议测试应直接请求。"""

import time

LOGIN_WAIT_SECONDS = []


def fixture_login(client, cache, payload):
    response = client.post("/login", json=payload)
    if response.status_code != 429:
        return response
    started = time.monotonic()
    while list(cache.scan_iter(match="api_rate_limit:login:sliding_window:*")):
        assert time.monotonic() - started < 65, "专属登录窗口未按原60秒期限自然过期"
        time.sleep(0.5)
    LOGIN_WAIT_SECONDS.append(round(time.monotonic() - started, 3))
    # 不清理键、不提高限流阈值、不替换响应或签发测试Token。
    return client.post("/login", json=payload)
