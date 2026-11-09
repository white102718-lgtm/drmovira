# ad_operation 广告操作消费者

1 进程 1 开发者:进程启动后 SCAN `ad_op:devq:*` 找有任务的开发者,SETNX `ad_op:dev_claim:{app_id}` 抢占,
线程池并发 5 执行(fast 队列优先,create 最多占 4 槽),队列空置 30s 释放认领并退出进程,由 docker 重启。
任务由 backend rpush 到 Redis(db3);无 dev_app 的消息进 `ad_op:route_pending`,空闲进程反查后转发。

操作成功后不在操作线程里刷 Doris(FB 配额退避会一睡 2~10 分钟拖垮线程池),只推
`ad_op:campaign_sync_queue`,由独立服务 `campaign_sync_consumer` 消费:优先用该账户的
企业(系统)开发者拉实体,定向刷该系列在 Doris 的状态/预算列;失败半点全量同步兜底。

## 日志与验证

```shell
docker logs -f ad_operation-ad_op_consumer-1          # 启动应见 "op_consumer 启动 (1 进程 1 开发者)"
docker logs -f ad_operation-campaign_sync_consumer-1  # 操作成功后应见 "[campaign_sync] ... 定向刷新 N 行"
redis-cli -n 3 keys 'ad_op:devq:*'                    # 有积压时可见按开发者分的队列
redis-cli -n 3 keys 'ad_op:dev_claim:*'               # 正在被服务的开发者
redis-cli -n 3 llen ad_op:campaign_sync_queue         # 待定向同步的系列积压
```

## 部署

容器数 ≥ 同时有操作的开发者数 + buffer(当前 ~17 个 dev,30 个够用;不够时调大 --scale 即可):
```shell
(cd deploy/ad_operation && docker-compose up -d --build --scale ad_op_consumer=30 --scale campaign_sync_consumer=3) > /tmp/ad_operation.log 2>&1; echo "exit=$?"; tail -40 /tmp/ad_operation.log
```

campaign_sync_consumer 无状态竞争消费(原子 LPOP),副本数按积压调;撞 FB 配额退避时一个副本会睡 2~10 分钟,多副本互不影响。
停止:
```shell
(cd deploy/ad_operation && docker-compose down)
```
