# 操作日志接口说明

## 记录范围

系统记录用户、角色、部门、菜单和通用IP规则的新增、修改、删除操作，同时记录重置密码和重置MFA操作。

每条日志包含：

- 操作人用户ID和显示名称快照。
- 业务模块、操作类型、操作名称、目标类型和目标ID。
- HTTP方法、请求路径、客户端IP和User-Agent。
- 成功或失败结果，以及失败业务码和安全提示。
- 操作发生时间。

系统不保存请求体、密码、JWT、MFA密钥、动态码或其他认证令牌。成功日志与业务写入位于同一个数据库事务：日志写入失败时业务写入也会回滚。业务操作失败时，失败日志在原事务回滚后使用独立事务保存。

## 数据库升级

部署新版 Java 服务前执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-system/src/main/resources/db/migration/V6__create_operation_log.sql
```

V6 创建 `sys_operation_log`，增加 `system:operation-log:list` 权限，并将权限授予有效的 `ADMIN` 角色。执行后管理员需要重新登录以刷新 Redis 权限快照。

## 分页查询

```http
GET /api/operation-logs?page=1&pageSize=20
Authorization: Bearer <access-token>
```

权限：`system:operation-log:list`

可选参数：

| 参数 | 类型 | 说明 |
|---|---|---|
| `keyword` | string | 匹配操作人、操作名称、目标类型、目标ID或请求路径 |
| `moduleCode` | string | 模块：`USER`、`ROLE`、`DEPARTMENT`、`MENU`、`IP_RULE` |
| `operationType` | string | `CREATE`、`UPDATE`、`DELETE`、`RESET_PASSWORD`、`RESET_MFA` |
| `operationResult` | integer | `0`失败，`1`成功 |
| `clientIp` | string | 精确匹配客户端IP |
| `startedAt` | datetime | ISO 8601格式的开始时间 |
| `endedAt` | datetime | ISO 8601格式的结束时间 |
| `page` | integer | 默认1 |
| `pageSize` | integer | 默认20，最大200 |

示例：

```http
GET /api/operation-logs?moduleCode=USER&operationType=UPDATE&operationResult=1&page=1&pageSize=20
```

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "items": [
      {
        "id": "2001",
        "operatorUserId": "1",
        "operatorDisplayName": "系统管理员",
        "moduleCode": "USER",
        "operationType": "UPDATE",
        "operationName": "修改用户",
        "targetType": "sys_user",
        "targetId": "15",
        "requestMethod": "PUT",
        "requestPath": "/api/users/15",
        "clientIp": "203.0.113.10",
        "userAgent": "Mozilla/5.0 ...",
        "operationResult": 1,
        "failureCode": null,
        "failureReason": null,
        "operatedAt": "2026-08-17T18:30:10.123"
      }
    ],
    "total": 1,
    "page": 1,
    "pageSize": 20
  }
}
```
