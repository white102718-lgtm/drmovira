# ad_materials workers

## 主流程

```
tasks/ad_materials/ad_materials_sync.py  (生产者: _enqueue_missing_materials)
          │
          ▼  rpush
  AD_MATERIALS_PRIMARY_FETCH_QUEUE_KEY
          │
          ▼  blpop
tasks/ad_materials/ad_materials_fetch_worker.py  (主消费: SDK 拉 URL → Mongo → Doris)
          │  失败 rpush
          ▼
  AD_CREATIVE_FETCH_QUEUE_KEY
          │
          ▼  blpop
tasks/ad_materials/ad_creative_scrape_worker.py  (兜底消费: Playwright 打开 iframe 抓 URL)
```

## 启停

所有命令在 `schedulers/` 根目录下执行。

### 生产者
调度触发,不单独启停(跟 `schduler_main` 一起跑)。

### 主消费 worker (ad_materials_fetch_worker)

```bash
# 启动
docker-compose -f deploy/ad_materials_fetch_worker/docker-compose.fetch.yml up -d --build
docker-compose -f deploy/ad_materials_fetch_worker/docker-compose.fetch.yml up -d --scale ad_materials_fetch_worker=2
# 停止
docker-compose -f deploy/ad_materials_fetch_worker/docker-compose.fetch.yml down
```

### 兜底消费 worker (ad_creative_scrape_worker)

```bash
# 启动
docker-compose -f deploy/ad_materials_fetch_worker/docker-compose.scrape.yml up -d --build
docker-compose -f deploy/ad_materials_fetch_worker/docker-compose.scrape.yml up -d --build --scale ad_creative_scrape_worker=4
# 停止
docker-compose -f deploy/ad_materials_fetch_worker/docker-compose.scrape.yml down
```
