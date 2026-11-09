# role 集合

**数据库**：user
**用途**：存储系统角色定义及对应的菜单权限列表。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 |
| `name` | String | 角色名称（唯一） |
| `remark` | String | 备注说明 |
| `permissions` | Array[String] | 菜单权限 ID 列表（对应 menu._id） |
| `status` | Int | 状态：`1`=启用，`0`=禁用 |
| `create_time` | DateTime | 创建时间 |
| `update_time` | DateTime | 更新时间 |

## 索引

- `name`（唯一）
