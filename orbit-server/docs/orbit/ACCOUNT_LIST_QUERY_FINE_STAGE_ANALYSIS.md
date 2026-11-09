# 061账户列表精细阶段诊断（同trace，非正式容量结论）

来源为20ef079fb1894068a0bc9d7c8de3ddf9运行目录809文件。容量形状为24execute、
items_count=page_size的schema2共801，排除最初200首读1个，其余8个基础/无list样本排除。
四档各200暖请求，同trace HTTP/list一致。10个固定标签每个暖请求均命中1次，
native resolver实测覆盖；Cookie resolver仍UNKNOWN，不代表完整Depends所有步骤都计入。
安全聚合含源码SHA256：`.runtime/account-list-stages-analysis-20ef079fb1894068a0bc9d7c8de3ddf9.json`。

## 墙钟分布

下表为每请求对应标签的均值/P95，单位ms；**存在嵌套，不能将整表相加**。

|标签|20|50|100|200|
|---|---:|---:|---:|---:|
|native_auth_resolve|138.079 / 176.374|149.395 / 207.549|185.891 / 332.407|203.728 / 310.804|
|rc_context_enter|45.267 / 148.727|50.616 / 119.581|60.065 / 128.706|85.561 / 247.949|
|rc_checkout（嵌于enter）|30.936 / 138.344|35.568 / 103.218|46.251 / 108.857|66.701 / 215.677|
|rc_isolation_options（嵌于enter）|14.184 / 19.625|14.907 / 22.257|13.659 / 28.477|18.710 / 38.939|
|json_response_construction|0.494 / 0.565|1.154 / 1.257|2.307 / 2.587|4.537 / 4.865|
|rc_transaction_exit|7.310 / 11.473|7.775 / 12.492|11.554 / 21.465|15.202 / 31.651|
|rc_context_exit|51.165 / 63.432|50.773 / 70.161|37.359 / 86.462|56.772 / 92.831|
|rc_connection_exit（嵌于context_exit）|31.557 / 41.497|31.749 / 45.354|22.741 / 51.368|34.873 / 71.361|
|rc_connection_close（嵌于connection_exit）|21.712 / 30.232|22.036 / 33.088|16.586 / 39.527|23.708 / 48.214|
|rc_isolation_reset（嵌于close）|14.362 / 21.660|14.511 / 22.596|10.736 / 26.646|16.367 / 34.983|

200行整请求均值：before_list302.287、service337.669（execute323.991、非execute13.681）、
list后到start120.294、末body后到app_end73.587、app_total855.452。
采用**同一请求的interval并集裁剪**再求差：before_list未覆盖均值12.998；
list后到start未被JSON构造/事务exit/RCcontext exit覆盖均值43.783。
RC enter扣checkout和options并集后仅0.150；RC context exit扣connection_exit后21.899；
connection_exit扣close后11.165；close扣reset后7.341。这些独占项也来自每个trace再聚合。
未覆盖不等于CPU，可能有框架、会话清理、调度及驱动等待。

## 一个真实尾部请求（不拼分位）

server app P95所在trace `e1e957d759054e0eb116544e611cd987`：
before_list576.471，其中native72.342、RCenter492.372（checkout484.121、options8.149），
before其余11.757；service304.824（execute292.476、非execute12.350）；
list后到start79.584，其中JSON4.486、事务exit38.964、RCexit8.475，剩余27.658；
start后到末body23.638，末body后48.451；app_total1033.035。
此请求尾部主要位于checkout区间，不是其JSON编码或reset；但checkout包含池等待、
连接建立/pre-ping、驱动和事件循环等待，尚不能直接等同池已耗尽。
其他真实请求也有reset内突发长尾，不能以此单条宣称所有请求同一根因。

原客户端HTTP P95为647.052/707.085/827.644/1015.936ms，无client trace关联，
只并列留档；不与服务端P95相减。ASGI最终诊断落盘不在app_total内，仍有扰动。
800请求保持24execute，seal全部0；不将它解释为百万身份资源性能已通过。

## 最小生产优化候选（未实施）

首选可审查的窄改是LoginService三个密码策略配置的连续Redis GET合为一次MGET，
仅当前请求复用这次返回的三个真实配置，保留原默认值、pwd_update_date判断和UTC到期计算。
源码get_sys_account_chrtype / __init_password_is_modify / __password_is_expired
确实分别发一个GET；native resolver均值138–204ms且每请求命中，值得减少两次串行往返。
这是静态可证的重复I/O，不是已测得“三GET占全部204ms”；不删前后令牌原子核验、
实时native版本或当前权限，不引入跨请求安全缓存。不影响独立调用这些helper的既有接口。
须新增值组合/缺失/非法配置/密码到期/时区与会话撤销回归，再按原数据四档重验，不能承诺必过。

RC设置+reset在200行均值约35ms（它们在每请求不同父区间，不能加其P95）。
若原阈值仍失败，可评审生命周期受控、默认READ COMMITTED的独立只读池，避免每次来回设置，
但这扩大连接/内存预算与数据源生命周期，非本轮直接改：不能改全局默认隔离级别或共享池
归还策略，也不能通过不reset把RC泄漏给原RR业务。应先测checkout等待、连接数/pre-ping
细分，当前事实不足以批准扩池或多worker。

JSON构造200均值4.537ms，暂无理由新增JSON依赖。事务exit可能提交或回滚，保留完整语义；
不为省十几毫秒跳授权/到期门禁。文件只读分析，无生产修改、DB或Git操作。
