# 完整规则正文校验与内部版本存储

## 字段和冻结

RuleWriteGuard严格接收产品RuleWrite的全部11字段，拒绝额外tenant_id、actor_id、state、revision等服务端字段。name做NFC和首尾空白规范化，1—80个Unicode码点且不含控制字符；ownership恰好包含owner_user_id和owner_team_id两个规范UUID。target_level仅CAMPAIGN/ADSET/AD，window仅TODAY/YESTERDAY/LAST_3D/LAST_7D；scope_snapshot_id和metric_profile_id均校验UUID格式。

cooldown_minutes为整数0—10080，max_daily为整数1—1000，不接受字符串、小数或null。logic/groups复用RuleConditions，schedule复用RuleSchedule，不允许完整请求绕过条件、调度互斥或上限。正文转换为递归按键排序的规范JSON和UTF8 SHA256，引用UUID转小写，数值阈值继续保留产品十进制字符串。冻结对象不随原JsonNode改变，toString不打印正文。

UUID格式通过不代表对象存在、授权有效或profile已验证。owner的身份映射、成员关系和内部规则数据授权已补齐（见[RULE_OWNERSHIP.md](RULE_OWNERSHIP.md)），指标profile的未验证定义目录已补齐（见[METRIC_PROFILES.md](METRIC_PROFILES.md)），范围和生产已验证profile仍无完整可信来源，所有规则草稿固定reference_status=PENDING_REFERENCES。没有HTTP创建/编辑/启用入口，也没有将草稿接入调度或分析。

## 内部写事务

RuleDraftStore仅接受内部可信调用方给出的tenant、若依actor和幂等UUID。当前已实时验证租户/若依用户/业务身份、数据角色及owner/team范围，不替代会话、menu/action和scope/profile鉴权；后续公共入口必须先建立这些检查。

创建必须id=null、expectedRevision=0，规则ID由服务端产生，状态DRAFT。更新必须规则属于该租户且版本匹配，DRAFT或PAUSED可编辑，ENABLED先暂停，ARCHIVED终态。任意正文或状态变更版本加1并清空current_simulation_id；不会沿用旧模拟。PAUSE仅允许ENABLED，ARCHIVE仅允许DRAFT/PAUSED。本组件没有ENABLE方法，传入ENABLE返回拒绝，不能用未验证模拟启用。

READ_COMMITTED事务依次锁定启用租户、预占/读取幂等记录、锁规则头、做版本和状态检查，再写头、不可变版本、事件及首次成功结果引用。幂等摘要包含tenant、actor、动作、目标、期望版本、正文hash和规范化人工原因；同键不同内容409。重放读取首次成功的不可变版本，即使当前头已被修订也不返回新正文。审计或任何后续步骤失败，头/版本/幂等预占一起回滚。并发相同创建只提交一份，并发相同revision编辑只有一个提交。

## 迁移、测试及范围

V005新增orbit_rule_draft、orbit_rule_draft_version、orbit_rule_draft_event、orbit_rule_draft_idempotency。所有字段和表有中文COMMENT，正文采用LONGTEXT+JSON_VALID保留摘要原串，时间UTC。仅在工作区隔离MySQL测试库执行；正式空库或升级须依次审核V001—V005，不修改参考项目数据库。

24项完整请求单测覆盖全部必填、服务端字段注入、名称Unicode/NFC/长度/控制字符、属性顺序与冻结、ownership/引用UUID、数字边界/类型、对象/窗口枚举及共享条件/调度约束。真实MySQL专项新增7项：版本及旧创建重放、幂等内容变化与旧revision回滚、相同创建并发、编辑CAS、事件失败全回滚、先暂停编辑及归档终态、跨租户与禁用租户拒绝重放。启用状态仅通过SQL fixture布置，不代表真实启用功能已实现。

首轮MySQL专项25项中1项测试助手错误：助手只收集ConfigurationException，未收集新增规则409异常，导致预期拒绝作为Future异常逃出。修正为收集明确的两种业务异常，保留“一次成功一次409”的断言，失败回执归档，不删测试或降低标准。最终结果见evidence/mysql-configuration-integration.json和evidence/rule-write-core.json。

尚未完成：范围/profile引用授权与身份维护公共入口、完整Rule公共读取/分页/筛选、规则菜单与编辑页、真实模拟/扫描及15分钟失效、可启用状态机、调度水位/租约/运行slot唯一、可信命中与分析事务接通。RUL-02/05/06整体不勾选，也不以内部版本存储替代真实业务验收。
