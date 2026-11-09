# 规则展示元数据：创建人/时间与归属真实名

当前新contract/store/routes及专属39纯测PASS（1.08秒）、四Python文件Ruff/format通过；实际SQL/HTTP尚未运行。主线注册静态路由后单独验MySQL UNION/CAST、真实权限与正向回读。不是完整规则模拟/启用/调度交付。

业务依据：原PRD-ORBIT.md:362要求保留规则创建人/时间，原列表/详情归属不能只让用户辨认UUID。原057_rules_definitions.sql头已有created_by原nativeID及created_at UTC毫秒；业务用户display_name VARCHAR50可空、团队name VARCHAR100。无需新迁移，原Rule15/Page4不增加字段。

## 固定API与SDK合同

GET `/api/v1/rules/display-metadata?rule_ids=<规范UUID逗号列表>`，原rules.read+可见Rule范围，1..200唯一小写完整UUID，顺序原样返回。不借users/teams/accounts/monitor/launch或目录下载权限。

成功200严格一键`items`；每项严格七字段：rule_id(UUID)、revision(1..MAX_SAFE整数)、owner_user_name(string|null)、owner_team_name(string|null)、created_by(原nativeID正整数)、created_by_name(string|null)、created_at(`YYYY-MM-DDTHH:mm:ss.SSSZ`)。user/creator名1..50码点，team名1..100码点，须已NFC/trim，无Cc/Cf/Cs/U+2028/29，不对坏存储值偷偷修正；坏值503 RULE_DISPLAY_METADATA_UNAVAILABLE。只读同tenant真实display_name/team.name，不借sys昵称、当前登录人、UUID或其他来源造名称；无映射为null，前端明确未记录。当前归属名称与历史creator不同字段，创建时间不随Rule编辑/归档变化。

空/缺CSV、空白、大小写不规范、重复ID、末逗号、超过200均422 FIELD_INVALID路径/rule_ids；重复query400 INVALID_STRUCTURE，未知query400 UNKNOWN_FIELD，指定tenant头403 PERMISSION_DENIED，任何非空GET正文400 INVALID_STRUCTURE。列表某一项不存在/foreign/不可见，整请求404 NOT_FOUND，不返回部分名称/数据。已失去read动作403，当前会话门禁沿原认证实现。

## 后端读取与安全

外层单一实际事务：authorize_rule(rules.read)→原RuleStore._clock SHARE→一批head JOIN精确当前version FOR SHARE OF h,v→逐项原require_rule_visible及RuleStore.public完整payload/hash/原字段校验→一次三个分支UNION名称批读→原revalidate_access→返回。

名称分别按当前tenant+owner UUID、creator原nativeID、team UUID读取，所有来源keys为最多200可见Rule的真实关联，三个分支各自严格tenant过滤，不全目录扫、不逐行HTTP或SQL N+1。目录名字只有显示作用，不补来源/config/目录写锁或改变Rule业务锁序。缺行/NULL显示未知；返回超出本次关联keys、重复别名或坏标签拒503。UNION的字符串ref_id、CAST与实际collation需主线真实MySQL验证，纯RowMapping不证明SQL已可执行。

导出`rule_display_metadata_routes.router`，必须在原动态`/{rule_id}`之前由主线注册；没有app/role/credentials或正式迁移改动。route strict边界后DataSourceRegistry.session(log_sql=False)和session.begin，再调用store.get(session,actor,parsed_tuple_ids)。只读GET不创建CSRF/幂等收据或Rule事件，不重新核当前profile可用性阻止旧定义展示。

## 验证与剩余交付

39pure覆盖CSV/唯一/200边界、UTC毫秒/NFC/nullable、真实SQLAlchemy RowMapping的200条结果仅三次SQL（clock/head-version/names）、原输入顺序、不借权限、混不可见整404、坏Rule/创建列/名字503、首末撤权、实际路由函数strictGET及单事务。框架配置/认证依赖隔离替身，未加载私有env，不声称真实SQL权限或HTTP已验。

下一真实工具七参由root串队：原Rule创建后批量metadata与数据库逐项对账、root creator与当前owner区别、edit/archive后created_by/created_at不变而revision更新、only-read USER无目录权限、mixedforeign整404、read撤权、非法GET、原八表只读不变及UNION字符串匹配。正向PAUSE须原ENABLED真实来源尚未接；DRAFT pause409只作负例，不能充当正向pause。技术ENABLED样本必须单独标明且保留原trigger，不冒enable成功。


## 实际UNION错误与定点修复

主线第三、第四轮在元数据首请求503；安全诊断实证DBAPIError errno1271、Store名字UNION执行处，属于混合collation。已将三分支全部九个输出显式转为utf8mb4/utf8mb4_0900_as_cs，creator原BIGINT以无长度限制CHAR转换，UUID和中文名称不lower、不截断、不替换。仍一次有界names批读，无权限/DTO放宽。实际MySQL复验仍待主线，不把SQL编译纯测当执行通过；父失败证据保留。生产固定安全异常诊断只含类别/errno/Store行号，原异常重抛，不输出SQL/params/消息。


## 第五轮真实闭环结果

主线原15/15全部PASS，11.15秒，原Rule15/Page4、真实中文名称/原native创建人/UTC毫秒、跨租户与混不可见整404、仅read权限及即时撤销、原规则八表只读全行不变均实际通过。本结果覆盖前三节待实际MySQL说明；具名主线回执与BUSINESS_FLOW保留完整限定范围。

前四轮失败不改写：第一、二轮分别停在getInfo错误的精确空权限假设，安全诊断证明status200且仅rules.read和3个结构空字符串，工具随后仅允许这些空项；第三、四轮元数据首请求503，第四轮实证DBAPIError1271，属于UNION collation冲突，随后九投影显式同utf8mb4/utf8mb4_0900_as_cs修复。第五轮才实际通过。未调用simulate/enable，不把DRAFT暂停409负向当ENABLED暂停正向；后者由主线独立技术状态夹具负责，不在本8组通过范围。
