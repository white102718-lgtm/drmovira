# 原规则定义表单组件

`src/views/orbit/rules/RuleDefinitionForm.vue`仅负责受控的原RuleWrite11字段编辑。沿用既有Element Plus表单与布局，没有新页面、菜单、router、权限判断替身或API请求。表单的submit不是后端已保存或规则已启用；原模拟、启停、调度仍由父页面和真实服务分别处理。

## 受控上下文

| prop                                                    | 父组件提供的真实内容                                                                                         |
| ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| modelValue                                              | 原11字段初始/已保存值，或null新建；组件不修改传入对象                                                        |
| ownerOptions                                            | id/name/team_id/team_name，optional available=false表示不可新选；不手填UUID                                  |
| profileOptions                                          | id/version/label及optional available；label仅父从真实version/source/id派生，不要求后端发明MetricProfile.name |
| savedContext                                            | 已保存owner/profile展示上下文，可保留当前选中项；不根据正文UUID自动造候选                                    |
| scope                                                   | id/label/count/owner_user_id/owner_team_id；count只能来自真实完整范围/manifest，未知null不补0                |
| timezones                                               | 父提供可选IANA值与可读label；例如可包含按参考日核对的UTC偏移                                                 |
| defaults                                                | 父在初始化时提供明确timezone/start_date/end_date；不存在时保留未填                                           |
| fieldErrors                                             | 原HTTP错误指针/说明；编辑后忽略旧意图的错误，父新错误到达重新显示                                            |
| readOnly/disabled/busy                                  | 控制只读、无权/不可编辑和保存等待；ENABLED先暂停的状态门禁由父设置                                           |
| ownersLoading/profilesLoading/ownersError/profilesError | 真实候选读取状态；加载、错误、空选项或当前项撤回不可提交                                                     |

同名版本的配置仍显示完整真实ID，不能把显示label当持久字段或唯一键。选择owner只从候选取其真实team；owner改变后清空旧scope引用并发ownership-change，父必须重新核完整双方交集后提供匹配的新scope。未核数量、0、50001或归属不匹配不能提交；50000只作为原合同数量边界，不表示组件测试完成了真实容量。

已保存scope可以由父传入真实旧manifest上下文复用，组件不冒充原snapshot creator、不访问或放宽原私有scope接口。scope-picker插槽得到ownership/disabled/scope；默认按钮只发choose-scope事件，没有内部读取其它模块的动作。

## 事件与意图

- submit(value)：原parseRuleWrite完整核验后的一份独立11键对象。金额、比率、计数阈值始终字符串，空值不补0，inactive调度字段明确null。
- cancel：取消或只读关闭，不提交、不请求服务；busy期间禁用取消以免把未知在途写误作已撤销。
- change：表单改动信号，父可撤销旧模拟资格/清理服务端错误；不是新配置版本或成功保存。
- ownership-change、choose-scope：只传当前候选归属，供父受控picker；不自行产生authority/权限。

父负责实际候选搜索/翻页、原动作权限、CSRF/幂等键/CAS、已有ENABLED规则先暂停、请求代次/取消及未知结果恢复。子组件不生成幂等键、不调用SDK写入、不把保存变成enable。

## 默认值与原出处

依据`data/ORBIT_Codex开发PRD/FIELDS.md`及`reference/03_原合同保留章节.md:198—215`，只应用有明确依据的表单初值；公开parser仍不补缺键。

| 初值/行为                                 | 原依据                                                                                                                                                     |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 新建规则、AD、AND                         | FIELDS.md:573/583/603                                                                                                                                      |
| 1组1叶、组内AND、spend、GTE，阈值空       | FIELDS.md:613/623/633/643；原03:201—205                                                                                                                    |
| LAST_3D，近3/7天含今天                    | FIELDS.md:653；原03:206                                                                                                                                    |
| INTERVAL、30分钟                          | FIELDS.md:663/673                                                                                                                                          |
| 转DAILY/WEEKLY时10:00；WEEKLY星期1        | FIELDS.md:683/693；转INTERVAL清time/weekday为null，转DAILY清interval/weekday为null                                                                         |
| 分析冷却60、每日最多5                     | FIELDS.md:733/743                                                                                                                                          |
| scope来自当前授权选择，不自动增加未来账户 | FIELDS.md:593；原03:200                                                                                                                                    |
| 时区/当天/当天+90天                       | 原基线FIELDS.md:703/713/723确有这些默认描述；本组件按主线决定不从浏览器UTC或硬编码Asia/Shanghai生成业务日期，由父可信初始化上下文落实，缺失可明确选择/填写 |

起止日期含首尾最多366天；调度IANA时区与账户当地业务日分离。三种频率保持完整7键/互斥null；组件不自行执行DST调度，后端缺失时刻跳过、重复时刻一次。规则根/组AND/OR、最多5组/每组10叶/总20均有操作边界和原parser提交校验。金额阈值在每个对象的自身账户币种解释，不换汇、不跨币SUM。

## 验证与缺口

原生ElementPlus挂载的专属测试覆盖默认/未填、原11/7字段、Decimal与null、保存上下文、换owner旧范围失效、范围未知/0/50000/50001、来源撤回/错误/加载、频率互斥、366/367天、20叶/5组/组10、错误指针、readonly/disabled/busy/取消。fetch为拒绝使用的监控替身，没有真实候选/SQL/HTTP或浏览器验收。

首轮17PASS/1FAIL是ElFormItem原错误DOM的短延迟尚未展示；保留字段断言，用有界vi.waitFor等真实DOM后18/18通过。后续补全11指标/6比较白名单及数字字段清空不补0，20/20通过（19.79秒，测试函数17.05秒）；再核DAILY/WEEKLY保留仍适用的用户时刻，仅清inactive字段，最终复验见冻结回报。类型检查与三文件格式检查另行执行；impeccable机械检测一次返回空列表，不等于真实视觉或交互验收。实际页面、真实helpers、三个视口/键盘/错误焦点与布局视觉检查由主线接力，不能用纯挂载或构建替代。原SDK31纯和后端定义22真实证据分别保留，不继承为Form联调通过。
