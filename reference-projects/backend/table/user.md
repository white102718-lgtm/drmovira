# user 集合

**数据库**：user
**用途**：存储系统用户账号信息，包含认证、权限、部门等。

## 字段说明

| 字段名 | 类型 | 说明               |
|--------|------|------------------|
| `_id` | ObjectId | 主键               |
| `username` | String | 登录用户名（唯一，最少 6 位） |
| `real_name` | String | 真实姓名（唯一，用于业务标识）  |
| `email` | String | 邮箱               |
| `hashed_password` | String | 密码哈希（bcrypt）     |
| `roles` | Array[String] | 角色列表（见枚举）        |
| `status` | Int | 状态：`1`=启用，`0`=禁用 |
| `department` | String | 所属部门             |
| `departments` | Array[String] | 可以看哪个部门的数据权限     |
| `ips` | Array[String] | 允许登录的 IP 白名单     |
| `create_time` | DateTime | 创建时间             |
| `update_time` | DateTime | 更新时间             |

## roles 枚举值

| 值 | 说明 |
|----|------|
| `admin` | 管理员 |
| `operator` | 投手 |
| `operator_leader` | 投手主管 |
| `developer` | 开发者 |
| `creator` | 创意人员 |
| `am` | 账户经理 |

## 索引

- `username`（唯一）
- `real_name`（唯一）
- `roles`
