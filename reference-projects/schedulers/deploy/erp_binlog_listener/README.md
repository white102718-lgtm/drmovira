# erp_binlog_listener

ERP(mpower)MySQL binlog 实时监听,把 `fbad_ad_task` / `fbad_ad_subtask` / `task_kpi_info`
的变更秒级同步到 mongo(platform_config / agent_line_config / material_category)。
捕获到行事件后提取 task_id,调既有的 `sync_erp_kpi_to_mongo(task_ids)`,
合并逻辑(只覆盖 MySQL 有值字段、pixel/page_id 只补空等)与定时任务完全一致。
代码在 `tasks/erp_kpi_sync/binlog_listener.py`。

- 位点存 redis key `erp_kpi_binlog:pos`,重启续读。
- 位点已被服务端清理(1236)时自动从最新位置重开。原 10 分钟定时任务已下线,
  监听中断产生的空窗手动补:`python -m tasks.erp_kpi_sync.erp_kpi_sync`(同步近 30 分钟更新)。

## MySQL 侧前提

- `log_bin = ON`
- `binlog_format = ROW`,`binlog_row_image = FULL`
- `binlog_row_metadata = FULL`(MINIMAL 时 binlog 不带列名,解析出来全是 UNKNOWN_COL,取不到 task_id)
- 连接账号需 `REPLICATION SLAVE, REPLICATION CLIENT` 权限(测试库用 root 已满足;prod 需 mpower 授权)

## 本地启动

```bash
cd schedulers
python -m tasks.erp_kpi_sync.binlog_listener
```

环境由 `DEPLOY_ENV` 决定(默认 dev)。

## 服务器部署

在 `schedulers/` 根目录下执行(与其他服务一致,`DEPLOY_ENV` 由服务器环境提供):

```bash
docker-compose -f deploy/erp_binlog_listener/docker-compose.yml up -d --build

# 停止
docker-compose -f deploy/erp_binlog_listener/docker-compose.yml down
```
