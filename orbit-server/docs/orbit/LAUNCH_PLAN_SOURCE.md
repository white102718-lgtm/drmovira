# 配置源与计划状态版本接力

`launch_plan_source.capture_plan_source`只供已按当前动作授权、并在同一外层事务锁定计划头的内部调用者使用。它不增加`launch.read/edit`要求，不签发预检许可，也没有开放validate/execute路由。

保存配置仍按原逻辑插入不可变`orbit_launch_plan_version`；未来纯状态转换递增外部Plan.revision，不复制配置版本。读取配置源使用现有复合主键倒序`LIMIT 1 FOR SHARE`取得最新真实版本，再核源版本不高于CAS头、摘要、完整规范配置和冻结拥有者一致。不按当前head猜一个不存在的配置版本，不退回更老的匹配hash。无需给原Plan增加响应字段，也不新增循环外键。

先读取版本摘要和JSON存储字节数，超限拒绝后才允许读取完整配置；MySQL展示JSON可能增加空白，存储读取界限为原五MiB的两倍，规范JSON仍严格五MiB。内部结果只保存不可变bytes；调用方需要工作副本时重新解码，修改副本不改变原配置源。

## 当前证据

- 27项纯边界通过：状态head与source分离、不可变工作副本、安全整数、拥有者/摘要/正文损坏、缺失历史、有界查询及外层事务要求。纯测试不证明数据库索引或锁。
- `python-launch-plan-source-http.json`真实28/28、12.77秒通过，其中新增6组配置源专项，原Task核心16组及初始化/退出6组。实际验证head 1→2→3仍指向source 1、配置保存后真实source 4、存量损坏拒绝并恢复、不回退旧匹配、缺失历史拒绝、复合主键计划及真实1205共享锁冲突。
- 初次真实28/28、12.65秒回执另存`python-launch-plan-source-http-initial.json`；随后仅调整工具格式和测试连接的EXPLAIN说明输出，再复验当前28/28。EXPLAIN时只临时关闭该连接sql_notes，finally恢复；不关闭错误或锁检查。

这里的状态转换由独占UUID库SQL夹具构造，仅证明读取接力；没有审计状态API、平台来源、完整预检或202受理通过。新模块尚待接入预检/提交公共Store。原T1隔离构建器的旧head==source限制保持，不能将它改名为生产构建器。

## 下一接入顺序

1. 纯冻结合同与真实AuthorityProvider明确完整输入及来源；外部来源缺失仅阻断对应实测。
2. 预检持久记录保存source_revision、validated_head_revision及完整冻结摘要；同事务CAS、审计、outbox及幂等。
3. 名称和分配内部核验接受已授权动作context，按配置source比较，execute不得暗加edit。
4. 完整私有manifest准备后，原execute短事务发布真实Task；前端成功预检后通过原GET重读CAS头，不能自行猜head+1。
