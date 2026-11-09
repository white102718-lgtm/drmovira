# tag_configs / fact_tags / inference_tags 集合

**数据库**：plat
**用途**：
- `tag_configs`：标签系统总配置
- `fact_tags`：事实类标签（如国家、区域等客观分类标签）
- `inference_tags`：推理类标签（由模型或规则推断出的标签）

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 |
| `name` | String | 标签名称 |
| `title` | String | 标签显示标题 |
| `tags` | Array[String] | 标签值列表 |
| `created_at` | DateTime | 创建时间 |
| `updated_at` | DateTime | 更新时间 |

## 软删除

`tag_configs` 删除时移入 `trash` 数据库。
