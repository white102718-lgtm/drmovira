# 广告户列表性能索引

广告户列表默认按 MongoDB `fb_ad_accounts.updated_at DESC, _id DESC` 分页；补充使用信息时按
`feishu_account_used_record.account_id IN (...)` 查询。生产或本地数据库升级后，由具备数据库权限的运维人员执行：

```bash
mongosh "$MONGODB_URI" scripts/dev/ensure-ad-account-mongo-indexes.js
```

脚本为幂等操作，并输出当前索引。验证默认分页是否命中排序索引：

```javascript
db.fb_ad_accounts
  .find({})
  .sort({ updated_at: -1, _id: -1 })
  .limit(100)
  .explain('executionStats')
```

当 `winningPlan` 使用 `idx_fb_ad_accounts_updated_id` 时，默认列表排序不会额外进行内存排序。

`keyword` 当前是跨多个字段的“包含匹配”（不加前缀的正则）；普通 B-tree 索引不能有效加速该语义。若关键词搜索仍是瓶颈，应改用 MongoDB Atlas Search / 文本检索读模型，而不是继续为每个字段增加常规索引。
