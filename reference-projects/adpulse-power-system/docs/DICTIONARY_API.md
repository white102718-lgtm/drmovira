# 字典配置接口

字典由字典类型和字典项组成。业务代码使用稳定的 `dictCode` 查询选项，不依赖数据库 ID。

## 业务选项查询

已登录用户可查询启用的字典类型及启用字典项：

```http
GET /api/dictionaries/AD_MEDIA/options
Authorization: Bearer <access-token>
```

响应示例：

```json
{
  "code": 200,
  "message": "success",
  "data": [
    {"value": "FACEBOOK", "label": "Facebook"},
    {"value": "GOOGLE", "label": "Google"},
    {"value": "TIKTOK", "label": "TikTok"}
  ]
}
```

结果按 `sortOrder`、创建顺序排列。字典类型不存在、已停用或已删除时返回资源不存在；已停用或已删除的字典项不会出现在结果中。

## 管理接口

以下接口要求 `system:dictionary:list` 权限：

- `GET /api/dictionaries`：查询字典类型，可使用 `keyword`、`status` 过滤。
- `GET /api/dictionaries/types/{id}`：查询字典类型及全部有效字典项。
- `POST /api/dictionaries/types`：新增字典类型。
- `PUT /api/dictionaries/types/{id}`：修改字典类型。
- `DELETE /api/dictionaries/types/{id}`：软删除字典类型及其字典项。
- `POST /api/dictionaries/types/{dictTypeId}/items`：新增字典项。
- `PUT /api/dictionaries/items/{id}`：修改字典项。
- `DELETE /api/dictionaries/items/{id}`：软删除字典项。

字典类型编码使用大写字母、数字和下划线；同一字典类型内的 `value` 唯一。所有管理写操作都会写入操作审计日志。
