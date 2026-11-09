# inference_tags 集合

**数据库**：plat
**用途**：存储推理标签类型及其标签值，用于素材的模型推断分类。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 |
| `name` | String | 标签类型名称 |
| `title` | String | 标签类型显示标题 |
| `tags` | Array[String] | 标签值列表（模型推断的分类结果） |
| `created_at` | DateTime | 创建时间（UTC） |
| `updated_at` | DateTime | 更新时间（UTC） |
