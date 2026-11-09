# material_folder_shares 集合

**数据库**：plat
**用途**：个人文件夹分享（只读授权）。owner 把自己的某个文件夹分享给其他人查看。

分享**不含子级**：只有被直接分享的那一个文件夹可见，其子文件夹不会跟着被分享。
被分享人在文件夹树的 `shared` 分组里看到这些文件夹，每个作为独立根节点平铺。

分享对象用 `full_name`，与 `material_folders.owner` 对称。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 |
| `folder_id` | ObjectId | 被分享的文件夹 id，指向 [material_folders](./material_folders.md) |
| `shared_to` | String | 被分享人 `full_name`（索引） |
| `owner` | String | 分享发起人 `full_name`，建立时写入后不再变更 |
| `created_at` | DateTime | 首次分享时间 |
| `updated_at` | DateTime | 名单最近一次覆盖的时间 |

## 索引

- 复合：`(folder_id, shared_to)`（唯一）
- `shared_to`——查「分享给我的」

## 约束

- 名单设置是**覆盖式**：不在新名单里的旧分享会被删除
- 自己不能分享给自己（`owner` 会从 targets 里剔除）
- 权限只读：被分享人可以看文件夹内素材列表，不能改名/移动/删除文件夹，也不能增删其中的素材

## 相关接口

| 接口 | 说明 |
|------|------|
| `GET /material-folders/{fid}/shares` | 查看分享名单（仅 owner） |
| `PUT /material-folders/{fid}/shares` | 覆盖式设置分享名单（仅 owner） |
| `DELETE /material-folders/{fid}/shares` | 取消对指定人的分享（仅 owner） |
