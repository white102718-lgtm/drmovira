# material_folders 集合

**数据库**：plat
**用途**：素材个人文件夹，最多三级层级。前端「素材管理」左侧文件夹树的数据源。

文件夹本身只存层级结构，**不存素材归属**——素材与文件夹是多对多，关系落在
[material_folder_links](./material_folder_links.md)。文件夹内的素材实体仍在
[materials](./materials.md) 集合（`scope=personal`）。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 |
| `owner` | String | 归属人 `full_name`（索引） |
| `name` | String | 文件夹名 |
| `parent_id` | String | 父文件夹 id（**字符串**形式的 ObjectId，非 ObjectId 类型）；一级目录为 `null` |
| `level` | Int | 层级，1 / 2 / 3，超过 3 拒绝创建与移动 |
| `created_at` | DateTime | 创建时间 |
| `updated_at` | DateTime | 更新时间 |

## 索引

- 复合：`(owner, parent_id)`

## 约束

- 最多三级：建子级时校验 `parent.level < 3`；移动整棵子树时校验 `子树最大层级 + 层级差 ≤ 3`
- 移动不能挂到自身或自己的子孙下
- 删除要求文件夹为空：既无子文件夹，也无 `material_folder_links` 引用

## 相关接口

| 接口 | 说明 |
|------|------|
| `POST /material-folders` | 新建（`parent_id` 为空则建一级） |
| `GET /material-folders` | 文件夹树，返回 `{mine, shared}`；`full_name` 参数供 admin 查他人 |
| `PUT /material-folders/{fid}` | 重命名（仅 owner） |
| `PUT /material-folders/{fid}/move` | 移动（含整个子树，仅 owner） |
| `DELETE /material-folders/{fid}` | 删除（仅 owner，非空拒绝） |
| `GET /material-folders/{fid}/materials` | 文件夹内素材列表（owner / 被分享人 / admin 可看） |
| `POST /material-folders/{fid}/materials/batch_delete` | 移出素材（有消耗或在投的会被 blocked） |
| `PUT /material-folders/materials/tags` | 给素材覆盖 `tags_new`（打在素材上，跨文件夹共享） |
| `POST /material-folders/publish` | 把文件夹内素材公开到公共库（`scope` 转 `public`，素材仍留在文件夹） |
