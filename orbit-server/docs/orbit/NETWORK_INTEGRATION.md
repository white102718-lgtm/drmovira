# ORBIT 网络HTTP、JWT、Redis与MySQL联合测试

## 环境与来源

MySQL沿用本项目独立13306实例。Redis使用[redis-windows社区Windows构建8.10.3](https://github.com/redis-windows/redis-windows/releases/tag/8.10.3)，包名`Redis-8.10.3-Windows-x64-msys2.zip`，SHA256为`af16df340525b431e9ec8dabfd625d5e7a233f82805b5418819904ea909c447f`，下载后已核对。它不是Redis官方Windows发行版，也不作为生产部署版本验收。

Redis二进制位于工作区`.toolchain/redis-it/Redis-8.10.3-Windows-x64-msys2`，仅监听`127.0.0.1:16379`，测试使用DB15，数据目录`.runtime/redis-it`。关闭RDB和AOF，不添加系统服务，不复用参考项目实例。

## 实际执行范围

`OrbitConfigurationNetworkIT`使用嵌入式Tomcat随机回环端口及Java HttpClient，运行真实若依JWT签名/过滤器、真实Redis会话与序列化、Spring Security方法权限、Controller、Service、MyBatis、MySQL和事务。平台探测传输保留受控fixture，不访问真实Meta/GPT/Claude。

测试程序核对MySQL与Redis数据目录属于本工作区，才创建随机`orbit_net_<UUID>`库并执行若依原SQL及V001至V018。JWT签名密钥和凭据主密钥分别在测试JVM内随机生成，独立且不输出、不写仓库、不经命令参数传递。这是测试fixture属性，不读取、复用或修改已有私有环境配置；应用私有变量仍遵从指定`.env.local`来源约定。

每轮只删除本轮生成的测试库、只撤销本轮创建的Redis会话；不执行FLUSHDB/FLUSHALL。测试结束关闭Tomcat，启停脚本只操作PID、程序路径和目录均已识别的本项目实例。

## 复验命令

从orbit-server目录运行：

```powershell
./tools/start-mysql-test.ps1
./tools/start-redis-test.ps1
python -u tools/run_network_checks.py --java-home D:/progress/adpulse-power-system/.codex-toolchain/jdk --maven D:/progress/adpulse-power-system/.codex-toolchain/maven/bin/mvn.cmd
./tools/stop-redis-test.ps1
./tools/stop-mysql-test.ps1
```

默认单测不连接这些实例。联合验证使用显式`orbit-network-it` profile，Failsafe指向未打包classes目录，避免Spring Boot可执行jar结构影响测试类路径。失败回执按时间归档；提交的回执不包含原始JUnit系统属性、JWT、主密钥或平台密钥。

## 用例

1. 真实签名JWT与Redis会话经网络访问元数据（11类、62字段）、新增、详情、列表、幂等重放、提交人工原因的只读测试、核对数据库READ_TEST原因、清除/停用和历史。验证数据库计数、版本、验证失效、防缓存、无凭据/密文回显与无重复提交请求体缓存。
2. 有效JWT对应会话被撤销后，真实HTTP401。
3. 普通非法Token及含敏感探针的恶意JSON Header，响应和日志均不带原始输入。
4. 篡改签名不可借用已有Redis会话。
5. 真实会话缺动作权限403；数据库租户授权撤销403。
6. Redis会话TTL到期后，有效JWT也不能认证。

## 本轮发现的实际缺陷

增加恶意JSON Header探针后，真实TokenService的原始异常日志包含了解码后的敏感输入，用例失败。保留失败回执后，将原日志改为固定说明加异常类型，不记录异常message或堆栈；令牌校验和响应语义未改变，修复后重跑通过。该修改仅涉及原TokenService日志边界，不改登录业务。

## 尚未完成

这是按生产组件组装的系统配置联合测试，不是整个RuoYiApplication或八业务模块启动验收。完整应用用户名密码登录、动态菜单和GPT配置弹窗另见BROWSER_INTEGRATION.md；验证码启用流程、所有页面和全部弹窗、完整会话撤权矩阵及外部平台质量/权限仍待单独验收。受控探测结果不能作为真实平台认证通过证据。元数据API单项测试完成不代表系统配置模块全部完成。
