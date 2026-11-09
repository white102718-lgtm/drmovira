# 媒介资产回收接口

## 业务边界

回收流程处理 `media_asset` 中已分配的真实资产。申请后资产从
`ASSIGNED` 进入 `RETURN_PENDING`，不再参与新分配。管理员完成回收时：

- `AVAILABLE`：解除使用人和来源申请绑定，重新进入可用库存；
- `DISABLED`：解除绑定并停用，不参与后续分配。

回收单保留资产、归属、原使用人、申请人和处理人快照，不随资产后续修改而变化。

## 权限

- 发起回收：已登录用户可回收分配给自己的资产；拥有
  `media:resource:return:manage` 的管理人员可代为发起。
- 查询、统计和完成回收：需要 `media:resource:return:manage`。
- V12 默认将该权限授予活动的 `ADMIN` 角色；执行迁移后需重新登录，刷新 Redis 会话中的权限快照。

## 接口

### 分页查询

`GET /api/asset-returns?keyword=&status=PENDING&assetType=PERSONAL&assetSubtype=wechat&page=1&pageSize=20`

`status` 可选值为 `PENDING` 或 `COMPLETED`。

`assetType` 支持库存主类型；`assetSubtype` 仅在筛选共用 `PERSONAL` 主类型的
`personal`（个号）与 `wechat`（微信号）时传入。

### 统计概览

`GET /api/asset-returns/summary`

### 发起回收

`POST /api/asset-returns/assets/{assetId}`

```json
{
  "reason": "项目阶段结束"
}
```

### 完成回收

`POST /api/asset-returns/{id}/complete`

```json
{
  "outcome": "AVAILABLE"
}
```

服务在事务内对资产和回收单加行锁，重复发起或重复完成会返回业务冲突，不会生成重复数据。

## 数据库升级

应用不会自动执行迁移。先按版本顺序执行 V9、V11，再执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-system/src/main/resources/db/migration/V12__create_asset_return_flow.sql
```

测试环境在仓库根目录直接执行
`bash deploy/apply-asset-return-v12-test.sh`。脚本会自动定位 V12，可幂等修复建表或授权中断导致的半迁移状态，并输出表、索引和权限验证结果。
