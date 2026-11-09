# material_commons 集合

**数据库**：plat
**用途**：公共素材库（素材师/投放师共享的模版库），前端「素材管理 → 公共素材库」的数据源。

与广告素材库 `materials` 完全隔离：独立集合 + 独立 MinIO 桶 `material-commons`，仅图片/视频，
不写 Doris、不参与广告消耗分析。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 |
| `filename` | String | MinIO 中的唯一文件名，`<前缀><md5前8位><后缀>`（唯一索引）；撞名不撞内容时追加 4 位时间戳后缀 |
| `basename` | String | 文件基础名（`filename` 去后缀） |
| `origin_filename` | String | 用户上传的原始文件名 |
| `filetype` | String | 文件类型：`video` / `image` |
| `file_md5` | String | 文件 MD5 哈希 |
| `sha3_256` | String | 文件 SHA3-256 哈希（索引），库内去重判定用 |
| `img` | String | Base64 缩略图（最长边 120px 的 JPEG），解码失败为 `null` |
| `width` | Int | 原始宽度，取不到为 `null` |
| `height` | Int | 原始高度，取不到为 `null` |
| `duration` | Float | 视频时长（秒），图片/取不到为 `null` |
| `user` | String | 上传人 `full_name`（与 `materials.user` 对齐；老数据字段名为 `uploader`，见 `script/rename_common_uploader.py`） |
| `tags_new` | Array[String] | 标签 ID 列表（对应 `tree_tags._id`），未打标签为 `null` |
| `created_at` | DateTime | 上传时间 |
| `updated_at` | DateTime | 更新时间 |

## 索引

- `filename`（唯一）
- `sha3_256`
- `created_at`（倒序，列表排序用）

## 相关接口

| 接口 | 说明 |
|------|------|
| `POST /material-common/` | 上传（图片/视频/zip/7z），压缩包解压后逐个入库，返回 `task_id` 轮询 |
| `GET /material-common/` | 列表（分页，`created_at` 倒序），只返回卡片渲染字段 |
| `GET /material-common/by_ids` | 详情（预览用），带 `origin_filename` / `tags_tree` / 现签 `url` |
| `PUT /material-common/tags` | 批量覆盖 `tags_new` |
| `POST /material-common/batch_delete` | 批量删除（按 `_id`，同时删桶对象） |
| `POST /material-common/zip` | 打包下载，返回 `task_id` 轮询 |
