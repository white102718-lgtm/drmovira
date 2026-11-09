# creative_run_tasks_img 集合

**数据库**：plat
**用途**：记录运行中的图片 AI 生成任务，用于查询进度和剩余时间。

## 字段说明

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `_id` | ObjectId | 主键 |
| `file_ids` | Array[String] | 输入图片素材 ID 列表 |
| `basenames` | Array[String] | 输入图片基础名列表 |
| `prompt` | String | AI 生成提示词 |
| `task_type` | Integer | 任务类型（1=多图修改，2=单图复刻） |
| `image_num` | Integer | 要生成的图片数量 |
| `model` | String | AI 模型（`qwen` 或 `google`） |
| `status` | String | 任务状态（`SENDING` / `STARTED` / `COMPLETED` / `FAILED`） |
| `real_name` | String | 创建者姓名 |
| `created_at` | DateTime | 创建时间 |
| `processed_at` | DateTime\|Null | 处理开始时间 |
