# 本地容量夹具配置与复现边界

仅用于 ORBIT 自有 `127.0.0.1:13306` 测试实例，datadir 必须精确为本项目 `.runtime/mysql-it/data`。不读取业务凭据，不改变已有预览、远程数据库或应用 worker 数。

原实例实际为 128 MiB InnoDB buffer pool、100 MiB redo，事务提交刷盘值为 1。原 44 组曾出现 200 行并发 P95 超过一秒和五万范围创建十秒 ReadTimeout；失败回执完整保留，不能因后续配置不同而覆盖。累计 `wait_free` 不是单请求根因证据。

容量档显式采用至少 1 GiB buffer pool 与至少 1 GiB redo，已较大配置不缩小；刷盘值仍为 1。工具先核 datadir、无活动 InnoDB 事务、调整后的内存与磁盘余量，再执行两个固定 SET GLOBAL，限时观察动态调整完成。部分应用和仍在调整分别记状态，不冒充成功。

在 `orbit-server` 目录显式运行：

```powershell
.venv/Scripts/python.exe tools/configure_mysql_capacity_fixture.py --apply
.venv/Scripts/python.exe tools/run_python_framework_checks.py --migration-through 60 --include-accounts --include-account-details --account-details-only --include-configuration-metadata --include-account-capacity --include-account-scopes
```

默认不带 `--apply` 只读；工具生成 `evidence/python-mysql060-capacity-profile.json`。后续容量报告记录实际全局 pool/redo/flush 值，阈值、原十秒 HTTP timeout、数据量、并发和断言均不改变。重启实例会恢复原启动配置，必须重新明确选择容量档；没有偷偷修改启动配置。

本档通过也只证明所记录配置和本机工作负载。身份百万资源、冷启动、深页、稀疏筛选和正式部署需分别验收；不能宣布默认 128 MiB 档已通过。

参考：[MySQL 动态缓冲池调整](https://dev.mysql.com/doc/refman/8.4/en/innodb-buffer-pool-resize.html)、[redo 配置](https://dev.mysql.com/doc/refman/8.4/en/innodb-redo-log.html)。
