# 启动中间件

- pulsar

```shell
mkdir -p /opt/pulsar/data/{zookeeper,bookkeeper,broker} && chmod -R 777 /opt/pulsar/data
#生产环境
(cd deploy/pulsar && docker-compose -f prod-docker-compose.yml up -d)
(cd deploy/pulsar && docker-compose -f prod-docker-compose.yml down)
#测试环境
(cd deploy/pulsar && docker-compose up -d --build)
```

- 启动redis

```shell
(cd deploy/redis && docker-compose up -d --build)
(cd deploy/redis && docker-compose down)
```

# 调试

在容器中可以用 `python -m test.t` 的方式运行
以生产环境运行`$env:w_env = "prod"; python -m tasks.ad_sync.ad_sync`
`python -m tasks.ad_operation.op_hourly_report`

# 启停ad_sync

查看日志
```shell
docker logs -f ad_sync_c-schedulers-c-1
docker exec -it ad_sync_c-schedulers-c-1 tail -f logs/log
docker exec -it ad_sync_p-schedulers-p-1 tail -f logs/log
docker ps --format '{{.Names}}' | grep ad_sync_c-consumer | xargs -I {} sh -c 'echo "=== {} ==="; docker logs --tail 50 {}'
```

```shell
#部署主定时任务
(cd deploy/schduler_main && docker-compose up -d --build)
(cd deploy/schduler_main && docker-compose down)
# 部署 ERP binlog 实时监听(mpower 平台/代理线变更秒级同步 mongo;已替代主定时任务里的 erp_kpi_sync,先于/随 schduler_main 一起部署)
(cd deploy/erp_binlog_listener && docker-compose up -d --build)
# 部署fb数据拉取, 要部署多个
cat deploy/ad_sync_new/README.md
# 部署fbBM同步资产拉取，可以部署多个
(cd deploy/fb_business_consumer && docker-compose up -d --build --scale fb_asset=40)
# 部署素材拉取 worker(fetch + scrape)
cat deploy/ad_materials_fetch_worker/README.md
# 部署素材上传到Facebook素材库
(cd deploy/fb_material_push && docker-compose up -d --build --scale fb_material_push=5)
# 部署广告操作接收 (1 进程 1 开发者)
cat deploy/ad_operation/README.md
# 部署拉取记录 worker(查看记录: 按账户+天拉取 FB 操作记录)
cat deploy/ad_config_worker/README.md
```
