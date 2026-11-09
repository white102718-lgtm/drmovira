# agent_line_config 集合

**数据库**：plat
**用途**：存储代理线（投放线路）的详细配置，包括投放链接、像素、预算限制等。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | String | 代理线名称（主键） |
| `package_url` | String | 投放链接（App Store / Google Play 等） |
| `pixel_name` | String | 关联的 Facebook 像素名称 |
| `page_id` | String | 公共主页 ID（创建广告时的默认主页，未配置则不预选） |
| `optimizer` | String | 优化师用户名 |
| `package_type` | String | 包类型：`W2A` / `PWA` / `Store` |
| `package_name` | String | 包名 |
| `enabled` | Boolean | 是否启用 |
| `auto_run` | Boolean | 是否自动运行操作 |
| `is_send` | Boolean | 是否发送执行 |
| `budget_cap` | Int | 预算上限（分） |
| `budget_floor` | Int | 预算下限（分） |
| `create_time` | DateTime | 创建时间 |
| `update_time` | DateTime | 更新时间 |
| `created_by` | String | 创建者用户名 |
| `updated_by` | String | 更新者用户名 |
| `delete_time` | DateTime | 删除时间（软删除） |
| `deleted_by` | String | 删除者用户名（软删除） |

## 软删除

删除时移入 `trash` 数据库。
