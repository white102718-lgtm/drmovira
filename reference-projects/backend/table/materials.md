# materials 集合

**数据库**：plat
**用途**：存储上传的广告素材文件信息（图片、视频等）。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 |
| `filename` | String | MinIO 中的唯一文件名（唯一索引） |
| `basename` | String | 文件基础名（哈希索引） |
| `origin_filename` | String | 用户上传的原始文件名 |
| `filetype` | String | 文件类型：`video` / `image` / `other` |
| `file_md5` | String | 文件 MD5 哈希 |
| `sha3_256` | String | 文件 SHA3-256 哈希（索引） |
| `img` | String | Base64 缩略图 |
| `user` | String | 上传用户名 |
| `country` | String | 国家标签 |
| `operator` | String | 投手/操作人 |
| `creative_editor` | String | 创意编辑 |
| `creative_planner` | String | 创意策划 |
| `is_green_material` | Boolean | 是否绿通素材（工单入库时冗余自 material_orders，直传素材无此字段） |
| `game_platform` | String | 游戏平台 |
| `tags_new` | Array[String] | 标签列表（索引） |
| `scope` | String | 可见范围：`public` 公共库 / `personal` 个人文件夹 / `tmp` 广告创意临时素材；老数据无此字段，视为 `public` |
| `source` | String | 来源：`order` 素材工单入库；直传无此字段 |
| `order_id` | String | 来源工单 id（`source=order` 才有） |
| `order_no` | String | 来源工单编号（`source=order` 才有） |
| `published_at` | DateTime | 公开到公共库的时间（`scope=public` 才有） |
| `created_at` | DateTime | 上传时间 |
| `updated_at` | DateTime | 更新时间 |

个人文件夹归属不在本集合，见 [material_folder_links](./material_folder_links.md)（多对多）。
公共素材库是另一张表，见 [material_commons](./material_commons.md)。

## 索引

- `filename`（唯一）
- `basename`（哈希）
- `sha3_256`
- `tags_new`
- 复合：`(created_at DESC, country, operator, game_platform)`
- 复合：`(is_green_material, created_at DESC, _id DESC)`

## 删除留痕（trash.materials）

删除是硬删：MinIO 对象和本集合文档都物理删除。删除前把文档快照写入 `trash.materials`，
**只作审计记录，不能还原素材**（文件已不在 MinIO）。

快照沿用原 `_id` 和除 `img` 外的全部字段（`img` 是 base64 缩略图，留下来副本体积翻倍），额外追加：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `deleted_at` | DateTime | 删除时间 |
| `deleted_by` | String | 删除人中文姓名（`user.full_name`） |
| `deleted_by_real_name` | String | 删除人 `real_name`，与本集合 `user` / `operator` 同口径 |
| `deleted_department` | String | 删除人当时的部门快照 |
| `source` | String | 删除入口：`batch` 素材管理批量删除 / `folder` 个人文件夹删除 |

索引：`deleted_at DESC`、`basename`

有消耗或在投的素材不允许删除（`blocked_material_basenames`），因此不会出现在本集合。
