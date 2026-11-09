# creative_materials_img 集合

**数据库**：plat
**用途**：存储用于图片创意生成的上传图片素材，通过哈希去重。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 |
| `upload_filename` | String | 用户上传的原始文件名 |
| `sha3_256` | String | 文件 SHA3-256 哈希值（唯一） |
| `basename` | String | 文件基础名（不含扩展名） |
| `unique_filename` | String | MinIO 中的唯一文件名（16 位 UUID） |
| `file_size` | Integer | 文件大小（字节） |
| `content_type` | String | MIME 类型 |
| `thumbnail` | String | Base64 编码缩略图 |
| `upload_time` | DateTime | 上传时间（UTC） |

## 索引

| 索引字段 | 说明 |
|----------|------|
| `{sha3_256: 1}` | 唯一索引，用于去重 |
