# Metrics公开接口与浏览器的隔离夹具

此模块只为原POST指标查询及页面的真实HTTP/浏览器检查提供独立技术样本。`SQL_ONLY_NOT_PLATFORM`不是Meta采集或生产发行，不把FIXTURE的verified值提升为平台验证。本批没有自行运行数据库、服务或浏览器，测试通过前不声明公开200或三视口完成。

## 父进程准备与child配置

入口为`tools/metrics_browser_fixture.py::prepare_metrics_browser_fixture(client, admin, headers, password, cache, database)`。主线只在本轮127.0.0.1:13306且实际DATABASE匹配`orbit_py_it_<32hex>`的UUID库调用。返回`kind/control/control_path/profile/query/registered_query_count/expected`；返回值不含密码、Token或连接串，不写控制文件或启动服务。

主线按已有隔离约定显式配置`ORBIT_PYTHON_TEST_METRICS_BROWSER=True`及`ORBIT_PYTHON_TEST_METRICS_CONTROL=<control_path绝对路径>`，默认不导入此工具。child可实例化`LazyMetricsReadProvider(path, enabled=True)`、`LazyMetricsExpectedProvider(path, enabled=True)`，再配置app.state的metrics_source_provider、metrics_expected_provider、metrics_result_budget；后者仍用主线显式ResultBuildBudget。指标目录沿用单独`ORBIT_PYTHON_TEST_METRIC_PROFILE_QUERY`隔离开关，不改变生产验证策略。

父进程必须先完成SQL样本与独立登记，最后以tmp+rename原子写控制文件，再允许原公开查询。没有控制文件时lazy wrapper返回503，不因启动早于seed而缓存一个假成功。只在首次实际消费时读取严格控制；之后每次委托仍在当前同事务session检查URL host/port/database、实际SELECT DATABASE及当前tenant。原RegisteredSqlReadSource逐头核完整23字段原文/hash及UNTESTED技术来源配置；RegisteredSqlExpected核独立预登记manifest原文/hash和全部有界流。任何未登记query、来源撤销或元数据变化仍拒绝；不依据来路head或任意query即时生成权威收据。

## 控制文件

固定位置为`orbit-server/.runtime/metrics-browser-fixture/<run_uuid>/control.json`。必须绝对路径、标准UUID目录、固定文件名、无symlink/junction，resolve后仍在此根。只读最多4096字节，重复JSON键拒绝。严格六字段：

```json
{
  "version": 1,
  "run_id": "<真实run UUID，等于父目录>",
  "database": "orbit_py_it_<32小写hex>",
  "tenant_id": "<本轮真实tenant UUID>",
  "read_registry": "it_metric_read_<16小写hex>",
  "expected_registry": "it_metric_expect_<16小写hex>"
}
```

文件不容纳凭据、SQL、模块名、导入表达式或自选DB host。上例是字段说明，不是可直接启用的真实控制文件。测试结束由主线清理当前UUID数据库和本轮控制目录；本工具不会删除其他数据库/历史路径，随机登记表保留在本轮UUID库至runner最终清理。

## 样本及有限操作清单

同一root拥有者/团队建立三个真实内部账户，分别USD/EUR/GBP。日窗口固定2026-01-01至2026-01-02，账户当地Asia/Shanghai，两日完整manifest。USD有21条真实不可变广告快照和42条AD日事实，第一条第二日改名为`中文指标名称%_!`，旧日名称及实体ID保留。EUR有两日完整empty cell与六源字段合法零证明；GBP只有独立预期对象与名称证明、没有capture cell，输出未知而不补零。registrations原样NULL，usage在首四数据集未定义仍NULL。

默认AD/SUMMARY共有22个实体（21USD加1GBP未知），page_size20可真实翻两页，DAY共有44条。全范围totals始终三币种：USD spend为字符串5040、去重核验广告21、registrations NULL；EUR spend字符串0、广告0；GBP spend NULL、核验广告0，缺失两日单元。GBP预期实体存在不等于其广告事实已核验，不能把缺失广告计为已核验数。其他数值/质量字段仍以原严格DTO及真实服务响应检查，不拿页内合计替代totals。

预先登记460个完整13字段原query：ACCOUNT/CAMPAIGN/ADSET/AD × 20/50/100/200 × SUMMARY/DAY × 原七排序 × ASC/DESC共448；另AD/SUMMARY/spend/DESC下q为“中文”“%_!”“不存在的指标”各四档共12。scope/channel/operator均null，日期与profile固定。cursor不参与原queryhash，原服务端签名下一页/历史上一页可沿该已登记查询消费。其他筛选不得被工具静默接受或现算授信。

root可用返回profile的真实version/id选择目录候选，按返回query日期输入；从广告账户等Tab查询四实体，再广告Tab翻20+2、四档查询、打开详情检查全部原字段及NULL。q=%_!必须只命中改名广告，仍汇总该实体完整两日，spend字符串240；q无结果仍保留独立预期单元的质量与币种信息，不凭无items补零。浏览器不能修改SQL或拦截HTTP模拟业务响应。

## 当前纯验证

专属31项纯测通过，覆盖安全路径/大小/重复键/严格flag与默认零SQL、Engine/owned Connection形状与实际DB/tenant不符拒绝、原delegate独立消费、460查询唯一13字段、各实体完整unit/member根、改名两日及空匹配仍保留unit。Ruff和格式检查通过。此证据不等于parent seed SQL、公开HTTP或浏览器通过；主线后续串行真实运行并独立归档结果。

首次真实公开队列保留失败回执`evidence/python-metrics-public059-fixture-first-failed.json`：原结果八核心已过，浏览器seed在publication来源UPDATE处失败。根因是048 `metric_publication_intent_guard`从INSERT起冻结source_config_id/revision/proof，并非仅PUBLISHED才冻结；旧helper先创建空来源再补来源违反该真实guard。修复仅在初始INSERT同时写完整来源三项，与原14档结果夹具一致，不更改正式guard/迁移/领域代码。新增初始完整来源纯测后共32项通过；仍待主线重跑实际seed/公开HTTP，不能由纯测声称修复已实测通过。
