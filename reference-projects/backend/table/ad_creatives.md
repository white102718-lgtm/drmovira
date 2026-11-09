# ad_creatives 集合

**数据库**：plat
**用途**：存储经过审核/处理后可用于投放的广告创意素材。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 |
| `basename` | String | 创意基础名（索引） |
| `sha3_256` | String | 文件哈希（唯一索引） |
| `user` | String | 关联用户（索引） |
| `updated_at` | DateTime | 更新时间（索引） |

## 索引

- `sha3_256`（唯一）
- `basename`
- `updated_at`
- `user`
