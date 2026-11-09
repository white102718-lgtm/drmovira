# 五万账户范围创建隔离诊断

本模块仅诊断已发生的原容量 POST 超过10秒，不改变客户端超时、五万成员、原44项断言或生产Store。当前32通过/1ReadTimeout/11未运行保留为失败；前置四档20并发P95通过不能替代范围冻结完成，也没有证据把超时归因于前端构建。

`tools/account_scope_capacity_diagnostics.py` 导入不启动数据库、不加载Store或私有环境。主线显式child开关调用 `uninstall=install_scope_create_diagnostics(output_dir)`；完成时可调用 `uninstall()`。路径固定为后端 `.runtime/account-scope-capacity-profile/<32位小写hex UUID>/`，拒绝其他目录及可见symlink/reparse祖先。

安装器只包装原 `AccountScopeStore.create`，每次调用临时包装该session实例的execute，原参数、SQL、结果和异常原样转发。finally恢复原本地execute，原为继承方法时删除临时实例覆盖；并行不同session的计数完全独立。每次create分配独立诊断文件，只输出固定SQL类别、调用成功/失败数、累计/最大毫秒、member批次和行数进度。每个member SQL完成以及最终退出时更新本次JSON；CREATE_RETURNED表示原create已返回，**并不表示外层commit或HTTP已发送**，member_rows_completed也只表示相应SQL返回，不能当持久提交数。异常仅记EXCEPTION/TIMEOUT/CANCELLED，不落异常类型文本、SQL、参数、请求正文、幂等键、Token、人员/账户/数据库ID。

诊断落盘失败不会覆盖原业务返回或异常；可写时保留固定diagnostic_write_failures计数。诊断文件写入自身有开销，不应把本档结果替代无诊断的正式容量复验。工具不设置全局SQL事件、不更新引擎/池或其他请求上下文，不执行任何额外SQL。

ReadTimeout后主线可调用 `collect_timeout_diagnostic(admin,database,output_dir)`：先严格127.0.0.1:13306、`orbit_py_it_<32hex>`及SELECT DATABASE()三重核对，再只按该数据库限定的performance_schema线程命令枚举计数、data_lock_waits等待数、INNODB_TRX事务数/锁行数/修改行数。没有读取SQL_TEXT、PROCESSLIST_INFO、连接字符串或凭据；结果仅固定计数字段，未知命令合并OTHER。该快照不是阻塞原因结论，超时瞬间也可能请求尚在运行或已取消，须结合create阶段和最终退出记录解释。主线负责捕获诊断自身权限/连接异常，不得用诊断异常覆盖原ReadTimeout证据。

当前仅护栏纯测和包装协议验证，不连接数据库/运行HTTP。实际MySQL视图可用性与五万范围时间线待主线显式开关串行运行；正常没有开关不导入或安装此诊断。

定向纯测33/33 PASS（0.77秒），Ruff/格式通过：含同实例execute恢复、成功/原异常/取消/Timeout原样传播、并行不同session计数隔离、失败批次不报完成、落盘失败不改业务、固定路径/reparse拒绝、13306/UUID/实际库护栏与仅安全聚合SELECT。另直接将当前Store的member INSERT用已安装SQLAlchemy asyncmy方言编译，实际产物匹配本机asyncmy的RE_INSERT_VALUES；驱动cursors.pyx:310匹配会走_do_execute_many而不是:329逐行fallback。但这只是实际源码/渲染协议证明，不能证明本次服务器确实只收50条INSERT，驱动仍可能按max_stmt_length拆包。当前模块没有为了诊断在业务成功/异常后追加SESSION STATUS查询，尤其取消/失效后绝不诊断重连。需要运行层确认时，主线可另审仅成功路径、同CID的SESSION STATUS差值，保持与本模块应用批次计数严格区分。
