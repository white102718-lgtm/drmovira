# 完整应用浏览器测试第二轮失败记录

回执：`application-browser-integration-*.json`中第二轮归档（executed_at与browser_summary.startTime可核对）。三个尺寸均未通过，无业务验收勾选。

- 1440：登录按钮在验证码配置请求完成前触发，页面仍在登录页。增加真实captchaImage响应完成和验证码表单消失的前置断言。
- 1920：Element Plus选择框内部readonly input被选中项遮盖，无法点击。改点可见的选择框容器，不使用force点击。
- 390：原若依移动菜单覆盖新增按钮；需实际点击原遮罩关闭菜单后操作页面，保留上游布局行为。

原始运行日志、页面快照只留本机runtime；仓库不保存含账号表单值的完整快照。
