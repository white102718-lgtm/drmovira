# fact_tags 集合

**数据库**：plat
**用途**：存储事实标签类型及其标签值，用于素材的确定性分类（如国家、品类）。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 |
| `name` | String | 标签类型名称（如 `country`、`category`） |
| `title` | String | 标签类型显示标题（如 `国家`、`品类`） |
| `tags` | Array[String] | 标签值列表（如 `["印尼", "泰国"]`） |
| `created_at` | DateTime | 创建时间（UTC） |
| `updated_at` | DateTime | 更新时间（UTC） |
