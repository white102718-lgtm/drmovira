# creative_tasks / creative_tasks_img / creative_run_tasks_img 集合

**数据库**：plat
**用途**：
- `creative_tasks`：AI 创意视频生成任务
- `creative_tasks_img`：AI 创意图片生成任务
- `creative_run_tasks_img`：创意运行过程中的图片任务

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 |
| `basename` | String | 任务基础名（哈希索引） |
| `prompt` | String | AI 生成提示词 |
| `status` | String | 任务状态：`pending` / `running` / `success` / `failed` |
| `video_num` | Int | 生成视频/图片数量 |
| `real_name` | String | 创建者姓名 |
| `results` | Array[Object] | 生成结果列表 |
| `created_at` | DateTime | 创建时间 |
| `updated_at` | DateTime | 更新时间 |

## 索引

- `basename`（哈希）
- `(real_name, status)`
- `status`
