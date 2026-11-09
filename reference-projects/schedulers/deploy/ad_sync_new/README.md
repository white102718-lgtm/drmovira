# ad_sync_new

所有命令在 `schedulers/` 根目录下执行。

启动命令把 stdout/stderr 都重定向到 `/tmp/ad_sync_new_<role>.log`,屏幕只看尾部 40 行,
避免 build 输出 + 多容器启动状态行刷爆终端。完整 log 在文件里随时查。

CPU 错峰:**新架构 1 dev / 进程后,account_consumer 和 dispatcher 都不再需要随机
sleep 错峰**(account_consumer 从 200 降到 ~25,dispatcher 从 20 降到 ~5,
同时启动的 Python import 量不会 spike CPU)。docker `up --scale` 一行起来即可。

## 新架构:1 进程 = 1 dev

account_consumer 新模型:
- 进程启动后通过 `SETNX ad_sync_new:dev_claim:{dev_id} TTL=180s` 抢一个 dev_id
- 进程内 ThreadPoolExecutor(50) 并发处理该 dev 的 account_queue
- daemon heartbeat 每 20s 刷一次 claim 的 TTL,进程崩 / OOM 最坏 ~185s 后被下个 worker 接管
- 队列连续 120s 空 → 释放 claim,等下个调度重新 claim

容器数选择:**容器数 ≥ 活跃 dev 数即可**(目前 ~17 个)。多出来的容器在 `consumer_run`
循环里轮询 claim 等机会,不会占额外 FB 配额(没 claim 到 dev 的进程不调 FB API)。
建议留 ~50% buffer 应对 dev 数增长 + claim 释放后的接管延迟。

## 分发者(dispatcher)

```bash
# 启动:dispatcher 走的是 blpop ad_sync_new:dev_queue → dispatch_dev,主要在等
# 消息,3-5 个容器够用(超过 5 个大部分时间会闲着 blpop)
docker-compose -f deploy/ad_sync_new/docker-compose.dispatcher.yml up -d --build --scale dispatcher=5 > /tmp/ad_sync_new_dispatcher.log 2>&1
echo "exit=$?"; tail -40 /tmp/ad_sync_new_dispatcher.log

# 停止
docker-compose -f deploy/ad_sync_new/docker-compose.dispatcher.yml down
```

## 账户消费者(account_consumer)

拆成两个车道(`AD_SYNC_LANE`):

- `account_consumer_hourly` 只 claim 今天的队列 —— **给当天成效预留专属容器**,review 再多也挤不进来,新 hourly 进来当场有 worker 接。容量 = 活跃 dev 数 × 1.5 左右。
- `account_consumer_review` 只 claim 历史日期的队列。**池大小就是 review 的并发上限**;同一 dev 的多天还会被 `review_dev_lock` 串成一次一天,跨 dev 并行。

```bash
# 启动:两组各自定容量(hourly 留足、review 按想要的回填并发给)
docker-compose -f deploy/ad_sync_new/docker-compose.account_consumer.yml up -d --build \
  --scale account_consumer_hourly=50 \
  --scale account_consumer_review=10 > /tmp/ad_sync_new_account_consumer.log 2>&1
echo "exit=$?"; tail -40 /tmp/ad_sync_new_account_consumer.log

# 停止
docker-compose -f deploy/ad_sync_new/docker-compose.account_consumer.yml down > /tmp/ad_sync_new_account_consumer.log 2>&1
```
