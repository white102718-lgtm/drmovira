# material_folder_links 集合

**数据库**：plat
**用途**：素材 ↔ 个人文件夹的归属关系（多对多）。

文件夹归属从 `materials` 文档里剥离到这张关系表，因此**一条素材可以同时被多个文件夹引用**
（例如同一个工单产出物分发给多个投手的个人文件夹）。`folder_id` 永远指向具体文件夹，没有根目录概念。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键，同时用作文件夹内排序键（`_id` 倒序 = 最新在前） |
| `material_id` | ObjectId | 素材 id，指向 [materials](./materials.md) |
| `folder_id` | ObjectId | 文件夹 id，指向 [material_folders](./material_folders.md) |
| `source` | String | 归属来源：`upload`（直接上传进文件夹）/ `order`（素材工单分发） |
| `order_id` | String | 来源工单 id，`source=upload` 时为 `null` |
| `created_at` | DateTime | 建立归属的时间 |

## 索引

- 复合：`(material_id, folder_id)`（唯一）——保证幂等，重复入库同一文件夹不会产生多条
- 复合：`(folder_id, _id DESC)`——文件夹内分页

## 生命周期

- **建立**：按 `(material_id, folder_id)` 幂等 upsert，已存在则不改动（`$setOnInsert`）
- **解除**：从文件夹移出素材时删 link；删完后若某素材再无任何 link，即为「孤儿」
- **孤儿处理**：孤儿且 `scope=personal`（未公开过）→ 连同 MinIO 对象与 `materials` 文档彻底删除；
  已公开到公共库的（`scope=public`）→ 保留为纯公共素材，只是不再属于任何个人文件夹
