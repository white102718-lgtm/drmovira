# ad_config_worker

广告配置 / FB 操作记录拉取 worker(Redis 队列消费者)。
backend 往 `AD_CONFIG_QUEUE_KEY` rpush 任务,本 worker BLPOP 消费,结果写回 mongo。
代码在 `tasks/ad_config/ad_config_worker.py`。

拉取 token 选择(`_resolve_personal_token`):在能访问该账户的个号(personal_accounts,
status=True)里,**优先选所属开发者带企业登录权限(accounts.account_usage.facebook_login)的个号**,
再要求个号 token、开发者 app_secret/proxy 齐全。同一开发者同时只跑一个拉取
(redis 锁 `ad_config:lock:{dev_id}`),抢不到锁任务回队尾。

## 本地启动

```bash
cd schedulers
python -m tasks.ad_config.ad_config_worker
```

环境由 `DEPLOY_ENV` 决定(默认 dev)。

## 服务器部署

在 `schedulers/` 根目录下执行(与其他服务一致,`DEPLOY_ENV` 由服务器环境提供):

```bash
docker-compose -f deploy/ad_config_worker/docker-compose.yml up -d --build

# 停止
docker-compose -f deploy/ad_config_worker/docker-compose.yml down
```
