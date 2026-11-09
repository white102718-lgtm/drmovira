# `biz_task.task_code` 生成规则（Python 对接说明）

## 1. 结论

`task_code` 由后端应用在创建任务时生成，不是 MySQL 自增值，也不是由数据库触发器或默认值生成。

当前格式为：

```text
TASK-{任务类型首字母}-{UUID字符串前12个字符的大写形式}
```

目前系统只有两种任务类型：

| `task_type` | 类型标识 | `task_code` 示例 |
| --- | --- | --- |
| `DELIVERY` | `D` | `TASK-D-A1B2C3D4-E5F` |
| `MATERIAL` | `M` | `TASK-M-0A12BC34-D56` |

完整编号固定为 19 个字符，可用下面的正则表达式校验：

```regex
^TASK-[DM]-[0-9A-F]{8}-[0-9A-F]{3}$
```

## 2. Python 等价实现

下面的实现与当前 Java 逻辑完全一致：

```python
from uuid import uuid4


TASK_TYPE_MARKERS = {
    "DELIVERY": "D",
    "MATERIAL": "M",
}


def generate_task_code(task_type: str) -> str:
    """生成与 AdPulse Java 后端格式一致的任务展示编号。"""
    normalized_type = task_type.strip().upper()
    try:
        marker = TASK_TYPE_MARKERS[normalized_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported task type: {task_type!r}") from exc

    uuid_prefix = str(uuid4())[:12].upper()
    return f"TASK-{marker}-{uuid_prefix}"
```

调用示例：

```python
delivery_code = generate_task_code("DELIVERY")
material_code = generate_task_code("MATERIAL")
```

## 3. 必须注意的兼容细节

Java 实现先执行 `UUID.randomUUID().toString()`，再取 `substring(0, 12)`。标准 UUID 字符串形如：

```text
a1b2c3d4-e5f6-...
```

因此，前 12 个字符是 `a1b2c3d4-e5f`，其中包含连字符。Python 必须使用：

```python
str(uuid4())[:12].upper()
```

不要使用以下写法，否则格式会与 Java 不一致：

```python
# 错误：uuid.hex 不包含连字符，结果会变成连续12位十六进制字符
uuid4().hex[:12].upper()
```

任务类型标识来自 `task_type` 的首字符。当前后端实际传入值为 `DELIVERY` 或 `MATERIAL`，分别得到 `D` 和 `M`。Python 代码显式限制这两个值，可以避免未知类型意外生成不受系统支持的编号。

## 4. 生成和入库时机

创建投放任务和素材任务时，业务服务会：

1. 校验创建请求；
2. 生成 `task_code`；
3. 将它和任务公共字段一起插入 `biz_task`；
4. 在同一事务中继续写入对应的任务明细、附件等数据。

数据库字段为 `VARCHAR(50) NOT NULL`，并通过联合唯一索引保证有效记录的编号不重复：

```sql
UNIQUE KEY uk_biz_task_code_deleted (task_code, deleted_at)
```

`deleted_at = 0` 表示有效记录；软删除后该字段为 Unix 毫秒时间戳。当前 Java 代码只生成一次，没有在唯一键冲突后自动重新生成并重试。UUID 前缀提供约 44 位随机量，碰撞概率很低，但批量导入或 Python 独立入库时仍应正确处理数据库唯一键冲突。

## 5. 对接建议

- 如果 Python 是通过现有任务创建 API 对接，不要传入或自行生成 `task_code`，由 Java 后端统一生成。
- 只有在 Python 必须复刻编号规则时，才使用本文的 `generate_task_code()`。
- 不要根据 `task_code` 推导数据库主键、创建时间或任务顺序；它只是展示编号。
- 不建议绕过业务服务直接写 `biz_task`。直接入库会跳过权限、引用校验以及任务明细的事务一致性处理。

## 6. 当前实现位置

- 生成逻辑：`adpulse-main/src/main/java/com/adpulse/main/task/service/TaskService.java` 的 `insertTask` 方法。
- 入库 SQL：`adpulse-main/src/main/resources/mapper/task/TaskMapper.xml` 的 `insertTask`。
- 字段和唯一索引：`adpulse-main/src/main/resources/db/migration/V10__create_task_center_tables.sql`。
