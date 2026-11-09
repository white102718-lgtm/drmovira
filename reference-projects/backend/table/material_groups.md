# material_groups 集合

**数据库**：plat
**用途**：用户创建的素材组，用于批量应用素材配置（标题、正文、CTA 等）到广告。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 |
| `name` | String | 素材组名称（同一用户下唯一） |
| `description` | String | 描述 |
| `tags` | Array[String] | 标签列表（索引） |
| `materials` | Array[Object] | 素材配置列表（见子字段） |
| `materials_count` | Int | 素材数量 |
| `username` | String | 创建者用户名 |
| `user_id` | String | 创建者用户 ID |
| `real_name` | String | 创建者姓名 |
| `created_at` | DateTime | 创建时间 |
| `updated_at` | DateTime | 更新时间 |

### materials 子字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `material_id` | String | 关联的素材 ID（对应 materials._id） |
| `title` | String | 广告标题 |
| `body` | String | 广告正文 |
| `call_to_action` | String | CTA 按钮类型 |

## 索引

- `(username, name)`（唯一）
- `(username, created_at DESC)`
- `tags`
