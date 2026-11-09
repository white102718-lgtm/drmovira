# ad_operations 集合

**数据库**：plat
**用途**：存储对广告的操作记录（预算调整、暂停、启动、删除、创建等）。

## 字段说明

| 字段名             | 类型       | 说明                                                      |
|-----------------|----------|---------------------------------------------------------|
| `_id`           | ObjectId | 主键                                                      |
| `type`          | String   | 操作类型：`budget` / `pause` / `start` / `delete` / `create` |
| `id`            | String   | 不同层级对象 ID（campaign_id / adset_id / ad_id）               |
| `level`         | String   | 操作层级：`campaign` / `adset` / `ad`                        |
| `value`         | Int      | 操作值（如预算金额，单位分）                                          |
| `time`          | Int      | 计划执行时间戳                                                 |
| `timezone_name` | String   | 时区                                                      |
| `ext_info`      | String   | 扩展信息                                                    |
| `auto_run`      | Boolean  | 是否自动执行                                                  |
| `is_send`       | Boolean  | 是否已发送执行                                                 |
| `dev_app`       | Object   | 开发者应用信息快照                                               |
| `dev`           | Object   | 开发者信息快照                                                 |
| `create_config` | Array    | 创建广告时的完整配置                                              |
| `data.batch_id` | String   | 一次批量创建的稳定 ID；系列、广告组、广告三个阶段共享，用于进度聚合           |
| `real_name`     | String   | 操作者名称                                                   |
