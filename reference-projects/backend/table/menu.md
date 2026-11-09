# menu 集合

**数据库**：user
**用途**：存储系统菜单树结构，用于前端路由和权限控制。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键（同时作为权限 ID 使用） |
| `name` | String | 菜单代码名（路由名） |
| `path` | String | 路由路径 |
| `component` | String | 前端组件路径 |
| `type` | String | 类型：`menu`=菜单项 / `catalog`=目录 |
| `status` | Int | 状态：`1`=显示，`0`=隐藏 |
| `pid` | ObjectId | 父菜单 ID（null 为顶级） |
| `meta.title` | String | 菜单显示标题 |
| `meta.icon` | String | 菜单图标 |
| `meta.order` | Int | 同级排序顺序 |
