# Rule列表与详情真实显示资料

新增SDK只调用`GET /api/v1/rules/display-metadata?rule_ids=<1..200规范小写UUID逗号列表>`，沿原rules.read，不借人员/团队/指标目录权限。请求拒空、重复、201、非规范UUID；正常响应仅items一键，成员固定7字段：rule_id/revision/owner_user_name/owner_team_name/created_by/created_by_name/created_at。items顺序与原请求完全一致，缺项/多项/错序整页拒绝。

用户与创建人姓名为null或NFC/trim完整1..50码点，团队为null或1..100；控制符/非法Unicode拒绝，不偷偷截断或替换名称。created_by是原native用户整数，不能用该数替代owner业务UUID。created_at固定服务端UTC毫秒Z，不能用浏览器时间或本次操作者填值。null明确“未记录姓名/团队”，不凭登录者或username回退。

RuleList每次成功读取原Page4后，对该页≤200个Rule ID发一次批量GET；不逐行N+1，不改变Rule15/Page4字段。Drawer读取原GET后单户请求。列表/详情各自metadata epoch、AbortController、loading/error，换页、筛选、认证/详情关闭丢弃晚响应。加载、失败、真实null分别显示；来源失败不得显示“原接口尚未提供”或伪空成功。可显式重试显示资料。

每次metadata revision与本次原Rule逐条核对，不把两个独立请求假装原子快照。漂移409明确要求重查；旧页不能进入详情，旧详情不能编辑/暂停/归档，不自动用新版CAS写入。metadata401/403或某ID整批404清旧列表/Drawer及标签；来源503不冒撤权、不发新权限门禁，仍可看原已授权Rule字段和显式读取失败。

动作未知恢复保持原业务body/key/IfMatch；显示资料不替换原意图或授予动作。原规则创建、编辑、暂停/归档结果仍由原接口与当前动作/范围验证，metadata不是写权限凭证。

当前SDK协议及List/parent/Runs挂载均用fetch/SDK替身，只有主线实际HTTP及内置浏览器回执可计真实姓名/时间显示；没有Meta调用、数据库或Git。定向日志位于`.runtime/rule-metadata-business-*`，首轮87/88为旧断言仍期待“原接口尚未提供”，已改为核实际metadata字段，保留first-failed原记录；没有删掉原创建cap晚回不能跨身份emit断言。
