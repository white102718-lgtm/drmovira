"""ORBIT合同错误只携带安全说明，禁止把平台响应、请求体或数据库异常传给前端。"""


class OrbitError(Exception):
    def __init__(self, status: int, code: str, message: str, pointer: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.pointer = pointer
