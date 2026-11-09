# creative_materials / creative_materials_img 集合

**数据库**：plat
**用途**：
- `creative_materials`：创意生成功能上传的视频素材
- `creative_materials_img`：创意生成功能上传的图片素材

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 |
| `upload_filename` | String | 用户上传的原始文件名 |
| `sha3_256` | String | 文件哈希（索引） |
| `basename` | String | 文件基础名 |
| `unique_filename` | String | MinIO 中的唯一文件名 |
| `file_size` | Int | 文件大小（字节） |
| `content_type` | String | MIME 类型 |
| `thumbnail` | String | Base64 缩略图 |
| `upload_time` | DateTime | 上传时间 |

## 索引

- `sha3_256`
