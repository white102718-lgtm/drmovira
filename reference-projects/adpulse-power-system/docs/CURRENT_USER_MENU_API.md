# 当前用户角色菜单接口

## 接口

```http
GET /api/menus
Authorization: Bearer <access-token>
```

`GET /api/menus/` 同样支持。接口只要求用户已经完成登录并具有有效的 JWT 和 Redis 会话，不要求菜单管理权限。

## 数据范围

接口根据当前用户的有效角色查询菜单，并同时校验：

- 用户启用且未删除。
- 用户角色关系未删除。
- 角色启用且未删除。
- 角色菜单关系未删除。
- 菜单启用且未删除。

返回目录和菜单节点，不返回按钮节点。某个已授权节点的父目录没有直接授权时，后端会自动补齐有效父目录，以保证路由树完整。按钮权限继续使用登录成功响应或 `/api/auth/me` 中的 `permissions`。

## 响应结构

返回值可直接作为 Vben `RouteRecordStringComponent[]` 使用，同时保留 `_id`、`pid`、`type` 和 `authCode` 兼容字段。

```json
{
  "code": 200,
  "message": "success",
  "data": [
    {
      "_id": "1",
      "pid": "",
      "name": "SYSTEM",
      "path": "/system",
      "type": "catalog",
      "authCode": "",
      "meta": {
        "title": "系统管理",
        "icon": "lucide:shield-check",
        "order": 10,
        "hideInMenu": false,
        "keepAlive": false
      },
      "children": [
        {
          "_id": "2",
          "pid": "1",
          "name": "SYSTEM_USER",
          "path": "/system/user",
          "component": "/system/user/list",
          "type": "menu",
          "authCode": "system:user:list",
          "meta": {
            "title": "用户管理",
            "order": 10,
            "hideInMenu": false,
            "keepAlive": false
          },
          "children": []
        }
      ]
    }
  ]
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `_id` | 菜单ID，字符串形式 |
| `pid` | 父菜单ID，根节点为空字符串 |
| `name` | 路由名称，使用 `menu_code` |
| `path` | 路由地址；数据库未配置时根据 `menu_code` 生成稳定地址 |
| `component` | 页面组件；普通组件自动补充前导 `/` |
| `authCode` | 菜单权限码，无权限码时为空字符串 |
| `type` | `catalog` 或 `menu` |
| `meta.title` | 菜单标题 |
| `meta.icon` | 菜单图标 |
| `meta.order` | 排序值 |
| `meta.hideInMenu` | `visible=0` 时为 `true` |
| `meta.keepAlive` | `cacheable=1` 时为 `true` |
| `meta.link` | 外链地址 |
| `children` | 子菜单数组 |

如果用户没有任何有效角色菜单，接口成功返回空数组：

```json
{
  "code": 200,
  "message": "success",
  "data": []
}
```
