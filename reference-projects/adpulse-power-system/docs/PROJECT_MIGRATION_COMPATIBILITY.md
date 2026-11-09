# 投放二组迁移应用兼容交付（2026-09-07）

## 已实现行为

- 优化师未提供、NULL 或空白时全量保存为 ID/name 均 NULL；姓名无 ID、非法或非正 ID、不存在或软删除用户均拒绝。
- 原停用优化师仅在数据库原 ID 未变时允许保留；缺省姓名优先保留原快照。新建、改选其他停用用户均拒绝，可以清空或换为启用用户，不修改账号状态或登录权限。
- 列表及详情通过同一次 SQL 返回 optimizerStatus；未分配或用户已删除时为空。前端正常显示未分配及停用标记，编辑抽屉局部补充历史选项，不向新建候选列表开放停用人员。
- 当前代理线列表增加编辑入口，创建、读取、全量更新使用 `/project/agency-lines` 正式接口。清空在 API 边界显式传 NULL，批量导入可不填优化师。人员候选按页读取启用用户。
- 产品信息上限为 2000 个 UTF-16 代码单元，与 Java String/@Size 一致；保留首尾空白和换行，纯空白仍拒绝。详情展示完整原文，产品短名称仍为原有独立摘要字段。
- 项目与代理线主数据支持 kwai，数据库字典值为 KWAI、显示 Kwai；代理线保存仍受启用字典约束，但项目平台集合仅作展示，不限制代理线选择、导入或 Google Sheet 同步。独立 ProjectPlatformCode 不扩大广告执行类型，广告预检/发布入口显式拒绝 Kwai 和未知媒体。
- 多人字段传入时为权威来源；仅未提供多人字段时回退旧单人字段。AM 空数组拒绝；数据专员空数组清空关系及主表兼容字段。成员顺序及主表首位镜像沿用现有规则。
- 保留项目可编辑状态、代理线归属与唯一性、PATCH 绑定语义及事务边界。没有增加 pending 项目限制，也没有全局更改项目类型或负责团队。

## 验证状态

| 项目 | 结果 |
| --- | --- |
| Java 格式化 | main 及依赖模块 Spotless 已通过 |
| main 模块完整验证 | `mvn -pl adpulse-main -am verify` 通过；121 项，101 项执行通过，20 项原有跳过 |
| 根目录 `mvn verify` | system 模块 216 项测试通过，随后被原有格式问题阻断；见下文 |
| 前端针对性测试 | 20 项通过，含真实编辑提交函数、历史停用选项、空值 HTTP 往返、批量导入、原文/多人/KPI/三平台往返及广告执行拒绝 |
| 前端生产构建 | `pnpm --filter @vben/plat build` 通过，未发布构建包 |
| 前端类型检查 | 未全量通过；HEAD 基线 542 条、当前 541 条，按文件/错误内容对照无新增，修复一处代理线适配器类型错误；工作区未重置 |
| 前端 ESLint | 配置初始化失败：`internal/lint-configs/eslint-config/src/index.ts` 的 `_configs.test is not a function`，未进入文件检查 |
| 前端格式化、差异空白检查 | 修改文件 Prettier、两仓库 `git diff --check` 通过 |
| 浏览器 | 本地服务已能到达登录页；没有登录会话，业务表单及不同屏宽的视觉验收未完成 |
| 数据库、部署 | 本次未连接数据库、未执行 SQL、未导入、未部署 |

根目录格式失败来自未修改的 `adpulse-system/src/main/java/com/adpulse/system/feishuorg/service/FeishuMessageNotifier.java` 和 `adpulse-system/src/test/java/com/adpulse/system/asset/service/ApprovalFeishuNotifierTest.java`。未为了本次改造格式化其他模块。

前端基线本身存在多处类型错误，包括菜单组件、画布、任务页面；项目页既有四处涉及 Table record、KPI readonly options、targetMax 空值的错误仍需单独修复。不能将构建通过描述为全量类型检查通过。仓库要求的 ui-ux-pro-max 技能在可访问技能目录中未找到，本次复用现有表单与组件并依据仓库清单检查；不宣称完成该技能或登录后的页面验收。

测试入口：后端 `ProjectServiceTest`、`ProjectOperatingMapperTest`；前端运行：

```powershell
node --test plat/src/domain/project/migration-compatibility.test.cjs plat/src/domain/project/agency-line-refresh.test.cjs plat/src/domain/project/operating-detail.test.cjs
```

测试使用合成数据和 HTTP/Mapper 替身，未导入生产快照。它们证明应用分支和 SQL 绑定契约，不代替真实 MySQL 回读及迁移后的页面验收。

## 手动 SQL 与发布顺序

1. 核实目标环境、现有表结构、多人关系表及启用字典。组织及人员已准备的环境不要重复建；应用代码不依赖写死的部门或用户 ID。
2. 人工审核并执行 `adpulse-main/src/main/resources/db/migration/V34__support_migrated_project_master_data.sql`。此文件与资料目录的 `迁移前置调整.sql` 内容一致，二者选择一份执行。脚本需要支持 DELIMITER 的 MySQL 客户端，遇错停止；DDL 不可依赖事务回滚。
3. 回读验收：optimizer_id/name 允许 NULL，product_info 容量至少 2000，KWAI 唯一且启用。执行 SQL 不代表应用已兼容。
4. 部署兼容的后端及前端，确认所有仍承接流量的旧后端实例已退出，再开放产生新格式数据的操作或开展迁移。
5. 在测试环境验收创建未分配、详情/搜索/导出、历史停用归属保留、清空/更换、多人增删、长原文及 Kwai 往返；保持终态权限和跨项目绑定限制。
6. 最后由独立迁移任务导入数据并逐项回读。新格式数据写入后，旧版本不再兼容空优化师及长信息，不应直接回退旧应用。

main 目录现有两个 V33 文件属于原有情况，本次新增 V34，没有改名或重复执行 V33。system 模块的脚本编号单独管理；应用不自动执行迁移脚本。

## 后续迁移任务的固定规则

- 来源 fbad-suger，tenant_id=1、liability_company=160；14 项目、373 代理线仅为 2026-09-07 基线，执行时重新核查增量。
- 仅本批项目使用 other（其他）和负责团队名称 MP投放部；不全局更新其他项目。
- 保留原项目状态和代理线状态，包括 pending 项目下的 active 代理线。
- 42 条无 optimizer_id 代理线保持未分配；其中旧姓名快照为“子美”的记录不能仅凭姓名补用户。
- 历史用户 302/303 保持停用，不创建重复账号、不开放登录；新增归属人员保持原有无登录权限配置。
- AM、数据专员写完整关系及顺序，主表镜像首位。关系 created_by/updated_by 必须由迁移任务显式指定合法审计操作人。
- 66X 数据专员保留周鹭、宋建；81G 的 AM 和数据专员保留汪子辉、黄怡琦。
- 7003-N5555 保留完整产品信息及 Facebook/TikTok/Kwai；本批代理线仍全部为 Facebook。
- KPI：14 项目各取一条当前生效客户 KPI；8 条从 JSON 恢复，不把15条历史版本重复写入当前 KPI。指标 CPP，旧比较符 2→`<`、5→`<=`，金额与比较符不能擅自改写，执行时重新核查生效日期。
- 巴西→BR、服务费9→9.00、优先级2→normal。应用改造未实施上述数据导入。
