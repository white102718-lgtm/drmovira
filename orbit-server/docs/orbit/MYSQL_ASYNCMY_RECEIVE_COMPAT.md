# Windows MySQL 大字段接收兼容与实测边界

2026-11-08。此项由真实 032 容量失败触发，容量上限及原断言没有放宽。

## 真实失败与修复

首轮精确 5,242,880 字节的计划已写入 MySQL，但第一次读取完整 JSON 时，asyncmy 接收回调抛 `BufferError`，随后 SQL 报 2013 断连。失败尚未进入分配求解。CPython BufferedProtocol 适配循环调用下一次 `get_buffer` 时仍可持有前一个 memoryview，asyncmy 原位扩展同一个 bytearray 因而失败。依据为 [CPython 3.13.15 protocols.py](https://github.com/python/cpython/blob/v3.13.15/Lib/asyncio/protocols.py)、[Proactor 接收实现](https://github.com/python/cpython/blob/v3.13.15/Lib/asyncio/proactor_events.py) 与 [asyncmy 0.2.16 接收实现](https://github.com/long2ice/asyncmy/blob/v0.2.16/asyncmy/connection.pyx)。确定性复现调用真实标准库适配器；普通随机端口 TCP 发送未必产生该分段，因此单次 TCP 通过不算排除问题。

`config/asyncmy_compat.py` 仅针对锁定 asyncmy 0.2.16 和 Windows 安装兼容方法：先调用原驱动方法，仅出现 BufferError 才把当前缓冲区复制到新的 bytearray，再复用原方法扩容。旧 view 的所有者和有效内容保持，原压缩/位置/收缩及 MySQL 解析逻辑沿用。没有修改 site-packages、全局事件循环策略或数据包限制，没有换同步驱动。

框架 `config.database` 与独立 SQL 检查器都显式安装。第 02/03 次尝试中，父进程 SQL 工具没有导入框架 database，兼容实际未安装，继续失败；不能据此声称类替换或 Cython 缓存机制已被证实。第 04 次真正安装后，大字段读取和求解通过，暴露了后一处独立缺陷：DAG 内部默认 JSON 空格导致合法边界配置膨胀、被 413 拒绝。改为原规范紧凑序列化，仍保留严格 5 MiB 校验；对应精确边界与多一字节拒绝回归已补。

## 实测与剩余范围

原始/兼容协议专项 17/17 通过。另用自有随机 loopback 端口和事件门控制真实 TCP 分段，剩余接收空间为 32,768 字节时发送 65,536 字节：原协议真实 Proactor 在累计 262,144 字节后出现 BufferError；兼容协议完整接收 5,242,880 字节、逐字节相同、0 回调异常。证据为 `python-asyncmy-receive-real-tcp.json`；没有修改 transport 或使用数据库。这项可重复负例与此前普通 TCP 通过并不冲突。

`python-launch-allocation-runtime-http.json` 是真实 MySQL/Redis/HTTP 隔离专项，包含精确 5 MiB 计划、10,000 槽、500 素材、完整兼容图分块与 10,000 条结果单事务发布。每次原始失败另存 `python-launch-allocation-runtime-attempt-01..04.json`，没有把失败父轮改成 PASS。

该专项使用明确的 ISOLATED_TEST provider，只验队列协议、真实授权、事务与容量，不证明 C 活跃素材引用、平台身份/能力或广告写入通过。SQL 输入/输出规模也不等于峰值 RSS、冷缓存或全模块并发容量验收。

驱动版本升级时应先运行原始/兼容缓冲区对照、独立 TCP 与真实 SQL 大字段专项，再决定是否移除此兼容；非 Windows 和其他版本不自动改写协议。失败日志只保留受控类型、源码位置和数字数据库错误码，不输出 SQL 参数、文件内容或连接凭据。
