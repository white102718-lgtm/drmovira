---
name: feishu_sheet_sync
description: 新增/修改「飞书表格 → 库」的同步任务。当用户要同步一个飞书文档(多维表格或电子表格)到 Mongo/Doris,或要给已有同步加表、改字段映射时使用。
---

# 飞书表格同步

读取层已在 `utils/feishu.py`,已落地的例子是 `tasks/feishu_sync/feishu_account_sync.py`
(MP媒介资料表四张工作表 → `plat.feishu_account_used_record`)。

## 先探测,再写映射

**不要**根据 URL 或用户口述判断文档类型和字段名,全部实测:

1. `resolve_spreadsheet_token(url, app_id=, app_secret=)` 拿真实 token
2. `list_sheets(token, ...)` 列工作表(sheet_id / title / row_count / column_count)
3. `read_sheet_rows(...)` 抽几行看列名和值的真实形态
4. 统计目标列的缺失率再定必填校验和唯一键

## 这个文档踩过的坑

- **wiki 链接的 token 不是文档 token**。`/wiki/{node_token}` 要调
  `/wiki/v2/spaces/get_node` 换 `obj_token`;`obj_type` 同时告诉你是 `sheet` 还是 `bitable`。
- **日期是 Excel 1900 序列号**(45918 → 2025-09-18),不是日期串,用 `sheet_value_to_datetime`。
- **单元格可能是段数组**:超链接/邮箱/富文本列返回 `[{"text":..., "type":"url"}]`,
  用 `flatten_cell` 展平,否则入库的是一坨 JSON。
- **同名列会互相覆盖**:一张表里出现两个"备注"是常态,`_dedupe_headers` 会加 `#2` 后缀。
- **row_count 远大于真实数据行**,末尾大片空行,靠空行过滤而不是 row_count 判断数据量。
- **同一字段的列名跨表不统一**:`账户ID` vs `账户id`;状态词 `在用账户` vs `使用中`。
  逐表配,别指望一套映射通吃。
- **同一列的值类型不稳定**,同一列有 int 有 str,做键前统一 `str()`。

## 电子表格没有稳定行 ID

行号(`_row`)随插入/删除漂移,**不能**做唯一键。用业务键(如 account_id),
入库前确认它在过滤后的数据里唯一。

## 增量

电子表格无法服务端过滤,只能全量拉。多维表格可以用原生表达式:
`CurrentValue.[日期]>=TODATE("2026-09-04")`。
