# 规则未来五次调度预览

独立SDK `src/api/orbit/rule-schedule-preview.ts`与组件`RuleSchedulePreview.vue`对接主线只读技术接口，已按主线窗口接入真实Form/Editor，未修改原Rule字段。

## 精确协议

POST `/api/v1/rules/editor-schedule-preview`，严格4键：action CREATE/UPDATE、rule_id、rule_revision、schedule。CREATE的id/revision必须null；UPDATE当前真实UUID与正safe-int版本。Schedule沿原7键：frequency、interval_minutes、time_of_day、weekday、timezone、start_date、end_date，不增加第8字段，不缺省互斥null。复用原Schedule严格解析与含首尾366日规则。

只提供当前真实CSRF，无If-Match、Idempotency-Key、写入重试或新资格。原CSRF/当前认证变化的失败显式显示。POST仅技术读取，不建立Simulation、Task、Rule版本或enable条件。

响应严格reference_at/timezone/slots/skipped_local_times四键；reference_at与utc_time保留UTC六位微秒Z，slots 0—5，local_time保留服务端秒级墙钟及offset。SDK核实际时间有序晚于reference、local offset与对应UTC及IANA时区一致；不从浏览器时区补值。跳过墙钟独立数组最多366，reason只DST_NONEXISTENT_LOCAL_TIME，不把它填成有效运行。所有时间来自服务端，客户端不生成五条，也不把真实空当错误。

传输15秒/256KiB为客户端有界预算，不替代后端真实性或容量验收。请求立即复制原Schedule，no-store，处理取消与认证迟到，不将读取错误标成写入未知结果。

## 组件接线

受控props：action、ruleId、ruleRevision、当前原Schedule、csrfToken、实际认证contextKey、permissionCodes、disabled。只在明确点击时读取。CREATE对应rules.create、UPDATE对应rules.edit，不借rules.read或其它模块。原调度尚未填齐时明确提示，不推断今日/平台时区。

任何Schedule、版本、对象、动作、认证上下文或权限变化立即abort并清旧结果；取消/卸载后迟到不能显示为当前。401/403清结果且阻止仅修改Schedule绕过拒绝；实际新Context或CSRF后可由用户再点击。503/409真实显示，不返回假空数组。界面呈现真实参考UTC6、IANA、实际0—5条与跳过DST，不包含配置/issuer术语。

实际最小接线：原RuleDefinitionForm新增可选named schedule-preview slot，传内部当前Schedule深复制；Editor在slot放组件并传当前真实action/rule/revision/CSRF/权限。源加载、保存未知、owner切换等使旧上下文禁用或清除，403事件由Editor清除完整敏感表单，不吞原SAVE/SCOPE pending。不能用泛change猜Schedule，不改变原RuleWrite11。父页只移除“预览未接入”过时提示，保留/rule-hits未接缺口。

## 有限验证

SDK13项、ElementPlus组件11项，共24定向纯测试。SDK用fetch替身、组件用SDK替身，验证协议/取消/迟到/授权反馈，不等于真实HTTP、服务端DST算法、实际调度或三视口。主线已有后端接口的实际证据需独立引用，不继承为本组件验收。未调用平台、共享DB或服务。

## 槽接线复验

Form21 + Editor24 + 父页17 + 预览SDK13 + 组件11，合计86/86 PASS（22.21秒）。增加当前未保存Schedule、深复制不反改原11字段、原版本/CSRF、owner切换取消、SAVE未知保留及预览403清完整Editor断言。前两次85/86失败均为父index旧“未接入”提示换行导致替换未命中，实际按完整换行断言定位后修复；失败log/JUnit分别保存first-failed与second-failed，不删除原断言、不延长超时。

结果路径：`.runtime/rule-schedule-slot-vitest.log`、`.runtime/rule-schedule-slot-junit.xml`；类型结果`.runtime/rule-schedule-slot-type.log`。仍只是SDK替身与组件挂载，真实专属HTTP/三视口由主线串行复验。

## 原型弹窗修正

原型要求后五次预览为弹窗，已由内联结果修正为原生ElementPlus ElDialog“预览未来5次运行”。入口留表单外显按钮；点击才打开，弹窗内显示加载、真实0—5条、错误、空库存及DST跳过墙钟。503留弹窗，401/403清敏感并关闭，外部仅短错误；当前父Editor仍沿access-denied清完整表单。主动关闭/取消立即abort并清结果，不自动重发或保存，用户再次点击才新查。Schedule/owner/context/版本/disabled变化均关闭清旧，焦点在closed后返回原入口。

测试使用真实ElDialog、aria-modal与公开有名role；内容从真实append-to-body dialog定位。初始modelValue=false，ElementPlus可保留display:none空overlay壳，不能把壳节点存在误判为已弹出；以实际不可见及空内容检查。关闭focus handler的挂载协议断言不代替主线真实浏览器键盘焦点验收。

弹窗最终复验：Preview14 + Editor24 = 38/38 PASS（20.58秒），type/四文件格式PASS，机械检查[]。记录`.runtime/rule-schedule-modal-vitest.log`、`rule-schedule-modal-junit.xml`、`rule-schedule-modal-type.log`。首轮37/38仅初始隐藏overlay壳误判为弹出，失败log/JUnit保留first-failed；修为当前model=false且实际不可见，原有名modal/加载/结果/真实X关闭abort/零重发断言全部保留。真实浏览器三视口仍由主线复验，挂载结果不抬升验收。
