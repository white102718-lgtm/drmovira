# PY06 D2：真实系列命名预留独立交付设计

## 原合同与边界

`contracts/openapi-current.json`：POST `/api/v1/launch-plans/{id}/campaign-names`，无请求正文，Idempotency-Key、X-CSRF-Token、If-Match必填，动作`launch.edit`，返回200原`NameReservation`，items只含slot_key/name/sequence，不加假task或预检hash。`reference/03_原合同保留章节.md`4.9与WORKFLOWS101约束上海命名日、来源变动失效、原子占号及旧任务名称不可覆写。

当前只实现内部命名占号；不冒充完整身份/能力/预算/素材分配/执行预检。不新建/修改共享路由、角色桥接或旧D1，注册由主线完成。原021的name_sequence/reservation/item完整复用，无新DDL。原渠道、产品、总代来源的权限与有效性沿真实Python服务复核，资料不从浏览器payload取得。

## 来源冻结与事务

1. 实时launch.edit和可信会话CSRF；无锁读取原计划并检查If-Match及DRAFT/VALIDATED。
2. 当前目录水位，实际拥有者仍启用、同团队且落在调用者本人/明确管理范围；从sys_user.nick_name读取昵称，空时回退orbit_business_user.display_name真实姓名，两者均空失败，不使用user_name冒充姓名。
3. 固定命名相关计划投影，只核真实账户/渠道来源；caller与实际owner都须当前accounts.read/channels.read及数据范围交集，账户1..500/同owner/team/币种/仍绑定，渠道启用/owner交集及产品/总代AVAILABLE关系。身份、素材、profile和metric不在命名阶段伪核；账户scope仍按现D1未接依赖503。
4. 取得launch clock写锁，再计划行CAS锁，锁后重新检查launch.edit、原配置hash/版本/状态、DB时间是否仍同一上海项目日。来源共享锁保持到同一事务结束。
5. 来源hash包含原plan payload hash、ownership、实际channel数据/版本、nickname/full_name、引用版本/账户与目录水位、展开系列slot及固定Asia/Shanghai口径；完整来源保存在不可变NAME_RESERVATION审计details.naming_source。API不回显内部权限快照。
6. 同键成功重放先重新授权和核当前来源；任何日期/来源漂移409 NAMING_PREVIEW_STALE，不用原键偷偷另占号。新键且完整plan_revision/day/source_hash相同直接复用原reservation，既不重命名也不重复审计。
7. 新来源取得tenant/channel/实际owner/上海日期唯一序列行，原子预留整个区间。30位DECIMAL上限、每层最多10000、完整生成名<=200码点，任何一项错误整事务回滚。每200条executemany，名称序号>=4位、9999后自然扩展。reservation/items/序列/审计/outbox/幂等同事务，没有部分成功。
8. 旧reservation/items不覆盖；当前输入变化通过新预留产生新id，历史任务继续引用旧id。`verify_current`是未来预检可调用的独立实时来源重验入口，当前仍需launch.edit；真正提交还须另外取得原execute/publish动作及完整预检，不能把此方法当执行许可。

## 容量与锁

展开先用原expanded_counts整数限额；账户/关联资料走有界集合，系列items最多10000，单批200；读回固定ordinal/最多10001防异常超限，原NameReservation不改摘要合同。原launch租户clock会串行化当前命名占号和计划写，首阶段保证正确性，不能把该串行点称容量通过；后续真实并发/EXPLAIN需主线证据。当前不存在跨平台网络请求和事务内等待异步求解。来源锁在launch前，避免反序。`verify_current`沿同一外层事务持锁，不能把其返回结果跨事务缓存当授权。

## 源码与验证

新文件：`python/orbit_api/launch_naming.py`、`launch_naming_routes.py`、`python/tests/test_launch_naming.py`、`tools/launch_naming_checks.py`。

23项纯测PASS，Ruff PASS：30位边界、9999自然扩位、UTC转上海午夜、来源/计划CAS独立失效、10000项50批写、超长Unicode名称不截断/不插部分项、成功原键实时重验、等锁跨午夜先拒绝。纯测不能计真实SQL/HTTP或UI验收。

主线注册入口`launch_naming_routes.router`。独立真实工具签名：`run_launch_naming_checks(client, admin, headers, fixture, cases)`，固定`LAUNCH_NAMING_CASES`8组。需001—022既有迁移及原用户fixture，026不是本工具必要依赖。工具只允许`orbit_py_it_[a-f0-9]{32}`孤立库：真实HTTP导入agent/product并创建渠道、SQL创建2个真实owned账户作为来源夹具；名字和菜单状态修改均在finally恢复，广告无外发。审计故障trigger精确限定plan.naming并finally删除。

具名8组：原无正文/200/真实4展开slot；同键及不同键相同输入复用；并发不同计划号段不重叠；昵称回退及历史名保留；上一项目日持久历史记录在当前HTTP不可重放；审计失败序列/名称/clock/key全回滚；渠道停用/当前动作撤销阻断成功原键；真实外租户plan与缺来源均不占号。跨日真实工具通过隔离历史日期fixture验证持久旧记录与当前DB日比较，绝不伪称实际等到午夜；实际UTC午夜换日计算与锁期间跨日边界另外由具名纯测覆盖。

此时未注册/未运行真实工具；前端命名预览、用户主动失效提示、完整预检集成仍待下一节点，不标D2整项验收。

补充静态审计修复：命名入口与内部verify_current先统一原规范UUID（允许大写归一化，拒花括号/裸32位），防止case-sensitive表下URL大写造成同输入预留查询遗漏。新增3纯测与真实工具第二组大小写同键/异键复用断言。最新26项纯测PASS、Ruff PASS；8组真实清单数量保持不变，仍未真实运行。命名新文件再次冻结。

## 主线真实MySQL/HTTP回执（最新）

主线`python-channel-launch-naming-http.json`：through029共92/92实际PASS，83.22秒，包含原B47、500拥有者9、D1 16、recipient4、新命名8和元数据/人员/初始化。命名原合同、同输入复用、并发区间、昵称回退、持久旧日期失效、审计整批回滚、即时撤权/停用、外租户/缺来源8组均有真实SQL/HTTP证据；26纯测只作为补充，不重复计业务验收数量。

这证明命名内部HTTP节点，不代表完整投放预检/执行通过。跨日真实组仍按上文明确隔离历史日期fixture边界；真实UTC换日/锁等待跨日由专项纯测覆盖。当前UI第01轮三视口在模板应用内部tab竞态失败，该产品bug已修；第02轮三视口在分享表单原因空值的提交前验证失败，仍待精确定位，不将后台92PASS混记浏览器PASS。


## 配置源与状态CAS接力（2026-11-08 20:54）

命名先按人员/账户/渠道来源加锁，再锁当前计划CAS头；随后通过launch_plan_source读取最新真实不可变PlanVersion。名称的plan_revision只绑定配置源，If-Match仍比较当前状态头，纯状态版本变化不复制配置或重复占序号。新的内部bind_naming_source不授予执行许可，缺配置历史或hash不符拒绝。

首次修复真实整档93/93、84.36秒通过，新增第九组通过SQL模拟纯状态头变更再调用原campaign-names HTTP，确认原配置版本、名称ID/完整名称及序列保持不变；模拟状态写入不是validate接口验收。具名回执python-launch-naming-source-head-http.json。后续又补原成功键在旧CAS重放先重核当前来源与权限，新键旧CAS仍409，相关纯测31/31、0.71秒通过；这项补充仍待真实复验，不能沿用首轮93项作为当前版本通过。

最终补充复验：python-launch-naming-source-head-replay-http.json以同一个原命名工具执行23/23、11.08秒通过，含原九组命名和必要人员/初始化。旧成功键按当前来源/权限重验后在旧CAS重放，新键旧CAS明确409且无新占号，当前source绑定修复已真实复验。专项减少无关模板等待，不删除命名检查，原93项跨模块回执保留历史。
