# 完整应用浏览器测试首轮失败记录

首轮回执归档在`application-browser-integration-2026-11-07T031427_0800.json`，无业务验收勾选。

Chromium已通过完整应用原登录和动态菜单，但点击Element Plus switch的隐藏checkbox时超时。改用可见`.el-switch`容器，不使用force。首轮Java包装器等待窗口不足，且手动提前关闭Spring测试上下文产生额外生命周期错误；后续限定总超时、由测试框架关闭上下文，仍严格验证浏览器退出码。

完整原始页面快照不提交仓库；仅保留失败原因，避免把表单账号内容带入证据。
