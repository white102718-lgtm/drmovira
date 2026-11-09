# department_config 集合

**数据库**：plat
**用途**：存储公司部门组织结构，支持多级树形结构。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 |
| `name` | String | 部门名称（全局唯一） |
| `parent_id` | String | 父部门名称（null 为顶级部门）。注意存的是父部门的 `name`，不是 `_id` |
| `create_time` | DateTime | 创建时间 |
| `created_by` | String | 创建人 |
| `update_time` | DateTime | 更新时间 |
| `updated_by` | String | 更新人 |

## 层级关系

- 通过 `parent_id` 引用父部门的 `name` 形成树形结构，与系统其他位置（`user.department`、开发者配置 `department` 等）统一用部门名称关联。
- 修改部门 `name` 时会级联更新所有子部门的 `parent_id`。
- 存在子部门时禁止删除该部门。

## 软删除

删除时移入 `trash` 数据库。
