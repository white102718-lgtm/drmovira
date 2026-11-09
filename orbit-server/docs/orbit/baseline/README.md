# ORBIT · Codex开发PRD包

当前范围：八模块、完整字段、Ant Design舒适布局、自动化投放上下单列。

## 阅读顺序

1. [PRD-ORBIT.md](PRD-ORBIT.md)：完整产品需求和开发边界。
2. [CONTRACT_OVERRIDES.md](CONTRACT_OVERRIDES.md)：已删除模块、引用资料、权限、旧条款冲突的唯一处理。
3. [FIELDS.md](FIELDS.md)及[当前API](contracts/openapi-current.json)：精确字段和127条路径。
4. [CODEX_TASKS.md](CODEX_TASKS.md)：可直接粘贴的Codex启动说明和11阶段任务。
5. [ACCEPTANCE.md](ACCEPTANCE.md)：36项需求验收计划及5条贯穿流程。
6. [VALIDATION_REPORT.md](VALIDATION_REPORT.md)：本包校验结果和仍需真实环境验证的事项。
7. [舒适版原型](reference/ORBIT_舒适版原型.html)：可离线打开的交互参考。

`contracts/openapi.json`是原保留123路径基线，只用于对照；开发使用`openapi-current.json`，新增4条引用目录路径。本包没有生产实现源码，原型不替代生产系统。

运行校验：`python3 validation/validate_prd.py`。只用Python标准库；不会连接平台或修改外部数据。校验文件与ZIP包含SHA256清单。
