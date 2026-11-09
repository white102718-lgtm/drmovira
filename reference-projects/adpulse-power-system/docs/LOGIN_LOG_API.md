# 登录日志接口说明

## 数据记录范围

系统在以下时机写入 `sys_login_log`：

- 密码认证失败，包括账号不存在、密码错误、用户停用、用户锁定和IP策略拒绝。
- MFA绑定或验证失败，包括挑战失效、用途不匹配、动态码错误和尝试次数过多。
- 不启用MFA的用户完成密码登录。
- 用户完成首次MFA绑定并登录。
- 已绑定MFA的用户通过动态码验证并登录。

创建MFA挑战只是中间状态，不记录为登录成功。日志不保存密码、JWT、MFA挑战令牌、MFA密钥或动态码。

## 数据库升级

部署前手工执行：

```bash
mysql -h 127.0.0.1 -P 3306 -u adpulse -p adpulse_system \
  < adpulse-system/src/main/resources/db/migration/V5__create_login_log.sql
```

V5 创建 `sys_login_log`，增加 `system:login-log:list` 权限，并将权限授予有效的 `ADMIN` 角色。执行后管理员需要重新登录，使 Redis 会话中的权限快照更新。

## 分页查询

```http
GET /api/login-logs?page=1&pageSize=20
Authorization: Bearer <access-token>
```

权限：`system:login-log:list`

可选查询参数：

| 参数 | 类型 | 说明 |
|---|---|---|
| `keyword` | string | 模糊匹配登录标识、用户名或显示名称 |
| `loginResult` | integer | `0`失败，`1`成功 |
| `authStage` | integer | `1`密码，`2`首次绑定MFA，`3`验证MFA |
| `clientIp` | string | 精确匹配客户端IP |
| `startedAt` | datetime | 开始时间，ISO 8601格式 |
| `endedAt` | datetime | 结束时间，ISO 8601格式 |
| `page` | integer | 页码，默认1 |
| `pageSize` | integer | 每页数量，默认20，最大200 |

示例：

```http
GET /api/login-logs?loginResult=0&authStage=3&startedAt=2026-08-17T00:00:00&endedAt=2026-08-17T23:59:59&page=1&pageSize=20
```

成功响应：

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "items": [
      {
        "id": "1001",
        "userId": "1",
        "loginIdentifier": "admin",
        "username": "admin",
        "displayName": "系统管理员",
        "authStage": 3,
        "loginResult": 0,
        "failureCode": 413,
        "failureReason": "MFA动态码错误或已过期",
        "clientIp": "203.0.113.10",
        "userAgent": "Mozilla/5.0 ...",
        "loginAt": "2026-08-17T15:32:10.123"
      }
    ],
    "total": 1,
    "page": 1,
    "pageSize": 20
  }
}
```
