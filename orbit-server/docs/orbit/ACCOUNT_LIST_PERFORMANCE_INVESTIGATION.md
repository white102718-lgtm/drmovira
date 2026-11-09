# 账户读取性能：当前证据与下一步

## 两种百万数据不能混淆

- 原账户容量档：50000账户、1000000条消费日事实，四档每档200个实际HTTP样本、20并发；成员范围另创建50000并读取250页。
- 身份摘要容量档：200账户各5000个身份资源，实际完整身份来源/封印链。此前P95优化后仍1.518秒，未达到1秒。账户消费档通过不代表身份档通过。

## 原失败与当前复验

| 原档 | 结果 | 证据 |
| --- | --- | --- |
| 060第一轮 | 32通过后50000范围创建ReadTimeout；原10秒不变 | evidence/python-account-scope060-capacity-first-failed.json |
| 060附范围计时第二轮 | 31通过后200行20并发P95=1.1412138秒；未进入范围创建 | evidence/python-account-scope060-profile-first-failed.json |
| 独立范围诊断 | 9/9，零日事实；创建5.189秒、250页53.419秒，完整7列hash一致 | evidence/python-scope-create060-focused-http.json、python-scope-create060-focused-profile.json |
| 最小同事务授权复用第一轮 | 原44/44；四档P95 0.596896/0.492337/0.942652/0.885452秒；创建5.105秒、创建加250页31.747秒 | evidence/python-account-scope060-auth-reuse-http.json |

复验没有增加worker、放宽超时/阈值、减少规模或剔除错误样本。以上仍是本机暖热点专项；没有将两次失败抹去，也没有证明所有变化由省去的两条SQL造成。票据内部篡改加强版154项纯测后，原44再次在200行P95=1.0106609秒失败（31通过、12未跑），见python-account-scope060-auth-hardened-failed/report.json；当前不得标稳定容量通过，继续固定标签分段诊断，不盲目重跑。

## 已核实和不能推断的事

官方RuoYi-FastAPI app.py的workers来自AppConfig.app_workers，env.py默认1；隔离runner也为单worker。不存在“生产默认多worker所以自动达标”的源码事实。若另测多worker，必须独立记录factory/reload配置、每worker连接池与内存预算、Redis撤权/限流和调度唯一性，不能覆盖单worker失败。

当前简化首屏EXPLAIN仅SELECT id且含unbound_at IS NULL，扫描201行约0.303ms，无filesort；实际_page为a.*和完整权限筛选，不能把简化计划当完整链证明。cProfile的39是总Session.execute次数，async函数ncalls还含恢复次数，不是39次授权。共享锁本身也不能证明读者串行。

原账户汇总已采用JSON_TABLE当前页账户驱动STRAIGHT_JOIN复合PRIMARY，仍需对实际200账户/20日查询做EXPLAIN，确认约4000条窗口事实访问。当前全链耗时包含连接池等待、SQL、逐行封印、DTO、JSON、压缩和发送，不能只凭一个P95归因。

## 后续分解与不变边界

1. 对实际_page、消费汇总、身份head/evidence/proof/seal/raw五组查询分别记录固定技术标签、次数、耗时和行数；不写SQL_TEXT、参数、ID或凭据。
2. 分开量连接池等待、SQL往返、Python逐行核验、响应编码/压缩、事件循环排队；在相同原数据/并发/阈值下比较。
3. 优先消除确证重复工作。首次list→prepare只允许同session/根事务/actor/action的一次性私有授权复用；Cookie自然到期、末段权限、分配到期投影及当前账户/来源/封印重核保留，无跨请求授权缓存。
4. 当前夹具同名账户、反复首屏仅证明暖热点；稀疏名称、深页、USER/TEAM路径和冷启动另列新增场景，不替换原失败样本。

阶段复验通过仅勾选对应有限证据；全模块验收和身份百万容量仍未完成。

## 后续实验与容量档

空 VENDOR 页跳过无意义的代称读取已通过六项定向纯测，非空页仍走原授权。原 44 组复验四档 P95 通过后，五万范围创建仍在原十秒发生 ReadTimeout，见 `python-account-scope060-empty-vendor-failed.json` 和对应 report，不能据列表通过勾选范围容量。

另一次 INSERT SELECT 成员写入候选在零日事实独立九项中通过，但创建 6.264 秒，未证明优于原 VALUES 的 5.189 秒；生产实现已恢复原 VALUES。候选 patch 和具名 server-copy 回执保留，不能把实验当已采用优化。

原实例只读核实 buffer pool 128 MiB、redo 100 MiB。现在显式另设 1 GiB/1 GiB 容量档，持久化刷盘保持 1，详见 [容量夹具复现](MYSQL_CAPACITY_FIXTURE.md)。新档复验与旧档失败分开记录，不据累计数据库计数推断已找到全部根因。ASGI/list 同请求诊断已接入可选测试开关，正式容量复验不启用诊断，不计诊断落盘为业务耗时。

明确 1 GiB 档原 44 组实际仍 FAIL：31 通过、1 失败、12 未运行；四档 P95 为 0.464582/0.656563/0.671175/1.061192 秒，最后一档超过原一秒。五万账户/百万事实与250页全集已经通过，范围创建未执行。证据 `python-account-scope060-1g-failed.json` 和 `python-account-scope060-1g-report.json`。没有因配置扩大宣称根因已解决；下一档单独启用 ASGI 同请求诊断。

后续细阶段同trace实测将native resolver、RC checkout/options/transaction exit/reset/响应构造分开；服务端P95所在单请求checkout484ms，但未证明池耗尽，详见ACCOUNT_LIST_QUERY_FINE_STAGE_ANALYSIS.md。生产只合并三个原密码策略GET为非事务pipeline一次execute（MGET会掩盖坏Redis类型，未采用）；原生183与真实Redis8通过，取消/撤权/到期和WRONGTYPE保留。原44再测200行P95仍1.012793秒失败，见`python-account-scope061-policy-pipeline-failed/report.json`，不是稳定容量通过，后续只扩测试池内诊断，未扩池/改worker。
