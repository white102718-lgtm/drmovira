# tree_tags 集合

**数据库**：plat
**用途**：存储树形结构的标签节点，用于素材标签的层级管理。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | String | 主键，树形结构 ID（如 `"1"`, `"1-1"`, `"1-1-1"`） |
| `title` | String | 标签标题/显示名称 |
| `parent_id` | String\|Null | 父节点 ID |
| `level` | Integer | 树形层级（默认 1） |
| `config_id` | String\|Null | 关联的标签配置 ID |
| `real_name` | String | 创建者姓名 |
| `created_at` | DateTime | 创建时间（UTC） |
| `updated_at` | DateTime | 更新时间（UTC） |

## 索引

| 索引字段 | 说明 |
|----------|------|
| `{parent_id: 1, _id: -1}` | 按父节点查询子节点 |
