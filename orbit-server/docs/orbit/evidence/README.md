# 实际执行证据

本目录只保存脱敏的实际执行结果。不保存密钥、私有环境、完整请求体、真实客户资料或平台Token。

业务条目测试/验收标为PASS时，`progress.json`对应阶段必须引用本仓库内的JSON回执，至少包含：

```json
{
  "item_ids": ["CFG-07"],
  "phase": "testing",
  "result": "PASS",
  "command": "实际执行的命令，不含凭据",
  "exit_code": 0,
  "executed_at": "带时区的实际执行时间",
  "environment": "实际环境和模拟/真实集成边界",
  "artifacts": ["脱敏报告路径"]
}
```

此示例仅说明格式，不是任何测试已通过的证据。工具检查不能替代人工核对回执真实性、用例充分性和环境边界。
