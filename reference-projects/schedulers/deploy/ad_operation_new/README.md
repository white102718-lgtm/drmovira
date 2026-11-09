# ad_operation_new 广告操作消费者（新系统）

与 `deploy/ad_operation` 同一套运行模型，跑的是 `tasks/ad_operation_new`。两者差异：

- 操作人身份查 `adpulse_system.sys_user`（MySQL，走 `erp_db`），不再查 mongo `user`；
  `real_name` 取 `english_nickname`，部门连 `sys_department.dept_name`。消息里只认 `user_id`，
  不再按 api_key 反查用户。
- 去掉了按开发者的操作间隔限流（原 `reserve_operation_slot`），消息取到即执行。
- 部门权限校验 `_check_permission` 未改，仍查 Doris `ad_daily_detail`；CREATE 无 level/id 照旧跳过。

1 进程 1 开发者:进程启动后 SCAN `ad_op:devq:*` 找有任务的开发者,SETNX `ad_op:dev_claim:{app_id}` 抢占,
线程池并发 5 执行(fast 队列优先,create 最多占 4 槽),队列空置 30s 释放认领并退出进程,由 docker 重启。
任务由 backend rpush 到 Redis(db3);无 dev_app 的消息进 `ad_op:route_pending`,空闲进程反查后转发。

⚠️ Redis key 前缀与老系统 `ad_operation` 完全相同。两套服务若连同一个 Redis 会互相抢消息，
必须确认新系统用的是独立 Redis(或先停掉老服务)。

然后 新系统的用户信息 查询的Mysql

## 日志与验证

```shell
docker logs -f ad_operation_new-ad_op_consumer-1          # 启动应见 "op_consumer 启动 (1 进程 1 开发者)"
docker logs -f ad_operation_new-campaign_sync_consumer-1  # 操作成功后应见 "[campaign_sync] ... 定向刷新 N 行"
redis-cli -n 3 keys 'ad_op:devq:*'                        # 有积压时可见按开发者分的队列
redis-cli -n 3 keys 'ad_op:dev_claim:*'                   # 正在被服务的开发者
redis-cli -n 3 llen ad_op:campaign_sync_queue             # 待定向同步的系列积压
```

## 部署

容器数 ≥ 同时有操作的开发者数 + buffer(不够时调大 --scale 即可):
```shell
(cd deploy/ad_operation_new && docker-compose up -d --build --scale ad_op_consumer=30 --scale campaign_sync_consumer=3) > /tmp/ad_operation_new.log 2>&1; echo "exit=$?"; tail -40 /tmp/ad_operation_new.log
```

campaign_sync_consumer 无状态竞争消费(原子 LPOP),副本数按积压调;撞 FB 配额退避时一个副本会睡 2~10 分钟,多副本互不影响。
停止:
```shell
(cd deploy/ad_operation_new && docker-compose down)
```
