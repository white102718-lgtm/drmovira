# material_category 集合

**数据库**：plat
**用途**：存储素材的树形分类结构（一级 → 二级 → 内容），供广告创建时选取素材内容。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 |
| `name` | String | 一级分类名称 |
| `sub_categories` | Array[Object] | 二级分类列表（见子字段） |

### sub_categories 子字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `id` | String | 二级分类 ID |
| `name` | String | 二级分类名称 |
| `contents` | Array[Object] | 内容项列表（见子字段） |

### contents 子字段

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `id` | String | 内容 ID |
| `type` | String | 内容类型：`text` / `image` / `video` |
| `text` | String | 文本内容或 MinIO 文件名 |
| `name` | String | 内容名称 |
| `remark` | String | 备注 |

## 软删除

删除时移入 `trash` 数据库。
