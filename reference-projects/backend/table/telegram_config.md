# telegram_config 集合

**数据库**：plat
**用途**：存储 Telegram 机器人通知配置，用于系统告警和消息推送。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 |
| `bot_token` | String | Telegram 机器人 Token（敏感） |
| `chat_id` | String | 目标聊天/群组 ID |
| `enabled` | Boolean | 是否启用推送 |
| `create_time` | DateTime | 创建时间 |
| `update_time` | DateTime | 更新时间 |

## 软删除

删除时移入 `trash` 数据库。
