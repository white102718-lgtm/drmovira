# 人工测试原因首轮回归失败

执行回执为network-configuration-integration按2026-11-07T03:56:17+08:00归档文件。默认单测先执行，配置Service测试的UPDATE审计断言被误加了READ_TEST人工原因预期；该既有用例失败，Failsafe网络用例未运行（tests=0）。

修复为仅在READ_TEST审计断言中核对人工原因，保留UPDATE原原因与摘要断言，不删除原用例。失败属于测试编辑错误，不以网络tests=0称通过。修复后重新运行默认测试和网络专项，结果看最新JSON回执。

提交前Spotless检查另外发现测试文件CRLF行尾不符，已统一行尾并通过检查；规范化LF后的SHA256前后相同（5812f07df4efc242c39cb5597e62f5d088299b404a08b42ede59ada153726baa），无业务或断言变化。
