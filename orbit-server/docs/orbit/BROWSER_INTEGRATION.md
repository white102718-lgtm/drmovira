# 完整若依应用与配置页面浏览器专项

## 运行边界

`OrbitApplicationBrowserIT`启动实际`RuoYiApplication`、Druid、MyBatis、原登录和动态菜单服务、JWT过滤器、配置服务；Chromium通过Vite访问随机端口的完整Java应用。真实MySQL和Redis使用本项目独立实例，不读取参考项目私有配置。

测试先核对MySQL与Redis目录属于本工作区、Redis DB14为空，创建随机`orbit_browser_<UUID>`数据库并应用若依原SQL及ORBIT V001至V018。只在该库关闭验证码，设置公开的fixture账号密码；JWT与AES主密钥在JVM内独立随机生成。仅外部平台ConnectionProbe为受控BLOCKED替身，不调用真实AI或Meta。

运行结束删除已知随机库与DB14明确的若依缓存前缀，不执行FLUSH。Playwright只允许向本项目`.runtime/browser-it`写入和清理产物，不复用已有前端服务；失败不自动重试、不强制点击不可见控件。

## 复验

```powershell
./tools/start-mysql-test.ps1
./tools/start-redis-test.ps1
python -u tools/run_browser_checks.py --java-home D:/progress/adpulse-power-system/.codex-toolchain/jdk --maven D:/progress/adpulse-power-system/.codex-toolchain/maven/bin/mvn.cmd
./tools/stop-redis-test.ps1
./tools/stop-mysql-test.ps1
```

需先在相邻orbit-web安装锁定依赖和Playwright对应Chromium。默认Maven单测不会运行浏览器；显式`orbit-browser-it`与网络集成profile分别限定测试类。网络专项启动配置另由专用Spring profile隔离，避免完整应用扫描纳入。

## 用例和证据

三个视口1440×900、1920×1080、390×844，分别使用真实登录、保留系统管理菜单、打开新增ORBIT配置菜单；新增GPT配置、替换密钥、KEEP不回显、两个真实页面并发旧版本拒绝并清理密钥输入、只读测试原因弹窗取消/空值拦截/确认、原因传入接口并在历史显示、只读连接BLOCKED、取消及确认CLEAR、停用、历史展开和状态摘要。

逐视口检查无页面脚本错误、无整页横向溢出、localStorage/sessionStorage无平台密钥。截图仅在密钥输入清理后手动保存；关闭trace/video和自动失败截图，原始表单快照仅保留本机，不提交。脱敏执行回执为`evidence/application-browser-integration.json`，之前的失败按执行时间归档。

## 不能据此勾选的范围

本专项不是全系统验收。原验证码启用流程、其余配置类型全部字段与条件、完整权限角色矩阵、真实GPT/Claude/Meta认证与模型质量、八模块未实现页面和弹窗仍需继续。BLOCKED探测替身不等于外部连接成功。结果以最新JSON回执为准，本文档存在不表示测试通过。

## 本轮结果

配置页三个视口的结果以最新回执为准，不以本文旧阶段的数量替代当前报告；同一完整应用测试类也包含范围HTTP专项，后者不是范围页面的浏览器验收。桌面列表/历史、390列表/历史截图已人工查看：保留原布局与菜单，窄屏表格在组件内部横向滚动，不据此扩大到所有字段的完整验收。失败定位过程和网络测试装配回归记录均保留在evidence目录。

AI建议策略新增两项分析限制：每个视口验证默认60/5、修改0/7、真实保存后重新打开保持0/7；这是配置持久化和表单测试，不证明规则执行器已限制调度。

三个输入输出限制字段在三个视口验证默认28/500/4096，保存7/20/1024后重新打开保持原值。只证明配置交互，不证明分析任务已经消费这些限制。

当前完整应用Java集成5项：页面浏览器包装1项（配置与范围各3个Playwright视口，共6个）和范围HTTP聚合4项；默认Java273。范围HTTP覆盖见[SCOPE_HTTP.md](SCOPE_HTTP.md)，本轮新增范围页面三视口，回执见scope-browser-integration.json；不含账户完整列表的跨页勾选。

新增范围页用例通过实际菜单路由，验证45个UNVERIFIED目录fixture、20条分页前后返回UUID一致、成员搜索空结果仍确认原45成员范围、重新查看/清除、页面筛选变化使旧选择失效并重新冻结11成员、非法UUID清单拦截。1440/1920/390均通过，截图只含公开fixture成员，未保存凭据。配置页3+范围页3合计6个浏览器用例，包装Java仍1项，另4项是HTTP聚合。

最新桌面及390窄屏成员弹窗截图已核对：等待弹窗动画及loading遮罩结束后采集；名称、长外部ID、范围数量及确认/关闭操作可见。窄屏表格在组件内部滚动，不发生整页横向溢出。此视检不扩大为全部账户页面的完整验收。

最新完整应用额外包含非管理员多功能角色合并HTTP用例；当前5个Java集成用例=4个HTTP聚合+1个浏览器包装。浏览器仍配置3+范围3，不把新增HTTP用例冒充新增页面验收。


2026-11-07预览并存检查：fixture固定使用18082，用户预览18081保持运行，禁止复用预览。browser/network profile生成ruoyi-admin-it.jar，不覆盖预览默认JAR。测试后预览四个PID不变、前后端HTTP200及默认JAR未在本轮改写，证据见evidence/preview-test-isolation.json。此隔离验证不代表公开跨租户验收。


2026-11-07跨租户HTTP专项新增2项，完整应用当前7项（范围HTTP6+浏览器包装1），浏览器仍为配置/同租户范围各3视口共6项。跨租户目标选择器尚未开发，不把API正向验证称作跨租户页面验收；参见SCOPE_HTTP.md公开跨租户小节。


公开GET /api/v1/audit-events与新增审计菜单页已接通范围冻结事件：跨当前授权租户稳定合并、九字段详情、筛选与20/50/100/200分页；全部目标版本绑定游标，未知历史必填身份显式503而不伪造或隐藏。新增MySQL9/真实HTTP3/浏览器3项通过，总Java280、MySQL135、完整应用10、浏览器9、网络6、前端21、台账12；保留三次失败回执。其他事件源、历史身份补证及完整SYS08仍待完成，不增加整项完成或验收勾选。 详见[AUDIT_QUERY.md](AUDIT_QUERY.md)公开接口与页面小节。
