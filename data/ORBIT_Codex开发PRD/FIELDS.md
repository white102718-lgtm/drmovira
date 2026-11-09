# 保留字段索引

JSON为精确数据源；该索引便于逐项验收。标识为module + key，不跨模块合并同名字段。

## 基础字段

### 通用.q

- label：搜索
- control：短输入
- required：否
- constraints：0至100字符；trim；拒绝控制字符
- default：空
- logic：名称前缀/包含按模块定义；ID精确；300ms防抖
- authority：P，外部字段叠加E

### 通用.date_range

- label：日期区间
- control：日期范围
- required：是
- constraints：1至93业务日；from<=to；不可超过当天
- default：近7日
- logic：超过93日转异步导出；日期端点均包含
- authority：P，外部字段叠加E

### 通用.cursor

- label：分页游标
- control：隐藏只读
- required：否
- constraints：不透明字符串<=2048字节
- default：null
- logic：绑定排序、筛选、权限版本与快照，禁止手改
- authority：P，外部字段叠加E

### 通用.page_size

- label：每页数
- control：单选
- required：是
- constraints：20/50/100/200之一
- default：50
- logic：改变后回第一页
- authority：P，外部字段叠加E

### 通用.ids

- label：批量选中ID
- control：多选
- required：是
- constraints：1至500个UUID；去重
- default：空
- logic：超限拒绝；选择快照须冻结权限与过滤器
- authority：P，外部字段叠加E

### 通用.revision

- label：对象版本
- control：只读
- required：是
- constraints：整数>=1
- default：1
- logic：If-Match或请求版本，过期409
- authority：P，外部字段叠加E

### 通用.reason

- label：原因意见
- control：长文本
- required：按动作
- constraints：必填时1至1000字符；可选时0至1000
- default：空
- logic：不可仅空白；所有危险动作和审批必填
- authority：P，外部字段叠加E

### 账户.account_id

- label：Meta账户ID
- control：只读/授权选择
- required：是
- constraints：外部ID为1至64字符数字串；act_仅适配器前缀
- default：无
- logic：不得JavaScript Number转换；同租户授权账户
- authority：P，外部字段叠加E

### 账户.name

- label：账户名称
- control：只读
- required：是
- constraints：同步文本1至255字符；保留原文
- default：平台值
- logic：超本地显示长度可省略但不丢原值
- authority：P，外部字段叠加E

### 账户.operator_id

- label：所属投手
- control：远程单选
- required：是
- constraints：一个启用用户UUID
- default：无
- logic：仅管理员分配；写入有效期历史
- authority：P，外部字段叠加E

### 账户.effective_from

- label：归属生效时间
- control：日期时间
- required：是
- constraints：ISO8601；账户当地下一业务日00:00或更晚；不得重叠
- default：下一业务日00:00
- logic：追溯修改需专门更正流程
- authority：P，外部字段叠加E

### 账户.currency

- label：币种
- control：只读
- required：是
- constraints：ISO4217三字母；服务器白名单
- default：平台值
- logic：不显示选择器；未知币种不能提交金额
- authority：P，外部字段叠加E

### 账户.timezone

- label：账户时区
- control：只读
- required：是
- constraints：有效IANA名称<=64字符
- default：平台值
- logic：不使用固定UTC偏移代替夏令时；界面UTC±HH:mm并可带地区名，存IANA值，按参考日期处理夏令时
- authority：P，外部字段叠加E

### 账户.remark

- label：备注
- control：长文本
- required：否
- constraints：0至1000字符
- default：空
- logic：本地业务字段，不发给Meta
- authority：P，外部字段叠加E

### 投放.plan_name

- label：计划名称
- control：短输入
- required：提交必填
- constraints：1至100字符
- default：新建计划
- logic：草稿可空；计划名不等于Meta系列名
- authority：P，外部字段叠加E

### 投放.account_ids

- label：账户
- control：远程多选
- required：提交必填
- constraints：1至500个；同币种；状态允许且授权有效
- default：空
- logic：冻结选择后复验每个账户
- authority：P，外部字段叠加E

### 投放.campaign.name

- label：系列名称
- control：只读自动生成
- required：提交必填
- constraints：1至200字符；渠道名称_用户昵称_YYYYMMDD_自动编号
- default：选渠道后生成
- logic：每个展开系列独立编号；预览冻结；重试不重新编号
- authority：P，外部字段叠加E

### 投放.campaign.objective

- label：系列目标
- control：能力单选
- required：是
- constraints：OUTCOME_SALES或OUTCOME_APP_PROMOTION；以能力包为准
- default：OUTCOME_SALES
- logic：目标变化清理不兼容组/创意配置并提示
- authority：P，外部字段叠加E

### 投放.campaign.buying_type

- label：购买类型
- control：单选
- required：是
- constraints：首期仅AUCTION
- default：AUCTION
- logic：其他类型只读不可选
- authority：P，外部字段叠加E

### 投放.campaign.special_ad_categories

- label：特殊广告类别
- control：能力多选
- required：是
- constraints：0至能力包上限；明确空数组表示无
- default：空数组
- logic：必须用户确认类别适用性；限制年龄等联动
- authority：P，外部字段叠加E

### 投放.budget_owner

- label：预算归属
- control：单选
- required：是
- constraints：CAMPAIGN/ADSET
- default：CAMPAIGN
- logic：不能同时给系列和组提交预算
- authority：P，外部字段叠加E

### 投放.budget_type

- label：预算类型
- control：单选
- required：是
- constraints：DAILY/LIFETIME
- default：DAILY
- logic：总预算必须有结束时间
- authority：P，外部字段叠加E

### 投放.budget_amount

- label：预算金额
- control：金额输入
- required：预算拥有者必填
- constraints：>0；最多币种小数位；产品<=1000000主币单位
- default：50
- logic：十进制定点；平台最小预算和租户上限取更严格者
- authority：P，外部字段叠加E

### 投放.spend_cap

- label：系列花费限额
- control：金额输入
- required：否
- constraints：空表示不设；填写>0且<=1000000主币单位
- default：空
- logic：不把0发送作默认清除；清除走专门平台适配
- authority：P，外部字段叠加E

### 投放.bid_strategy

- label：竞价策略
- control：能力单选
- required：是
- constraints：服务端支持集合；首期LOWEST_COST_WITHOUT_CAP
- default：能力默认
- logic：不提供任意文本；有出价需求再启用配套字段
- authority：P，外部字段叠加E

### 投放.adset.name

- label：广告组名称
- control：短输入
- required：提交必填
- constraints：1至200字符
- default：广告组1
- logic：名称不做唯一键
- authority：P，外部字段叠加E

### 投放.country_codes

- label：投放地区
- control：搜索多选
- required：是
- constraints：1至50个ISO3166-1 alpha2；去重
- default：无
- logic：映射targeting.geo_locations.countries
- authority：P，外部字段叠加E

### 投放.age_min

- label：最小年龄
- control：整数
- required：是
- constraints：18至65；<=age_max
- default：18
- logic：特殊广告类别按平台限制禁用/覆盖，须明确展示
- authority：P，外部字段叠加E

### 投放.age_max

- label：最大年龄
- control：整数
- required：是
- constraints：18至65；>=age_min；65显示65+
- default：65
- logic：不是允许所有国家/目标该年龄范围的承诺
- authority：P，外部字段叠加E

### 投放.locales

- label：语言
- control：远程多选
- required：否
- constraints：0至20个服务器语言ID
- default：空表示不限
- logic：不可传中文名称给Meta
- authority：P，外部字段叠加E

### 投放.placements

- label：版位
- control：能力单选
- required：是
- constraints：AUTO；首期不开放手工组合
- default：AUTO
- logic：适配器按锁定版本实现自动版位
- authority：P，外部字段叠加E

### 投放.optimization_goal

- label：优化目标
- control：能力单选
- required：是
- constraints：目标/账单事件/目的地允许的枚举
- default：能力默认
- logic：禁止自由文本
- authority：P，外部字段叠加E

### 投放.billing_event

- label：计费事件
- control：能力单选
- required：是
- constraints：对应优化目标的合法枚举
- default：能力默认
- logic：由能力包限制，不能跨目标复用
- authority：P，外部字段叠加E

### 投放.attribution_spec

- label：归因设置
- control：能力单选
- required：是
- constraints：服务器profile引用，不接收自由JSON
- default：账户支持默认
- logic：分析和采集记录profile版本
- authority：P，外部字段叠加E

### 投放.page_id

- label：主页
- control：账户资源单选
- required：是
- constraints：一个已授权外部ID 1至64字符
- default：无
- logic：逐账户验证，不能所有账户共用无权限主页
- authority：P，外部字段叠加E

### 投放.pixel_id

- label：像素或数据集
- control：账户资源单选
- required：网站转化必填
- constraints：一个已授权外部ID
- default：无
- logic：目标允许时写promoted_object
- authority：P，外部字段叠加E

### 投放.conversion_event

- label：优化事件
- control：能力单选
- required：转化目标必填
- constraints：经能力验证的事件枚举
- default：PURCHASE候选
- logic：应用目标改为app事件，不默认用网站像素
- authority：P，外部字段叠加E

### 投放.application_id

- label：应用ID
- control：账户资源单选
- required：应用推广必填
- constraints：一个有效外部ID
- default：空
- logic：与应用商店URL和系统相符
- authority：P，外部字段叠加E

### 投放.object_store_url

- label：应用商店URL
- control：URL输入
- required：应用推广必填
- constraints：1至2048字符；HTTPS；允许商店域名
- default：空
- logic：不与网站落地页混用
- authority：P，外部字段叠加E

### 投放.start_time

- label：开始时间
- control：日期时间
- required：是
- constraints：有效本地时间；提交至少未来5分钟
- default：当前加10分钟
- logic：按账户时区转UTC；预检过期重算
- authority：P，外部字段叠加E

### 投放.end_time

- label：结束时间
- control：日期时间
- required：总预算必填
- constraints：>start；最长366天；日预算可空
- default：空
- logic：夏令时不存在时刻拒绝，重复时刻需选offset
- authority：P，外部字段叠加E

### 投放.ad.name

- label：广告名称
- control：短输入
- required：提交必填
- constraints：1至200字符
- default：广告1
- logic：含自动后缀仍校验
- authority：P，外部字段叠加E

### 投放.ad.title

- label：广告标题
- control：短输入
- required：首期链接创意必填
- constraints：1至100字符
- default：空
- logic：展示建议长度与硬性上限分离
- authority：P，外部字段叠加E

### 投放.ad.body

- label：广告正文
- control：长文本
- required：首期必填
- constraints：1至2000字符；允许换行
- default：空
- logic：纯文本；禁止执行HTML；平台更严格则阻止
- authority：P，外部字段叠加E

### 投放.ad.description

- label：补充描述
- control：长文本
- required：否
- constraints：0至300字符
- default：空
- logic：不支持该版位则忽略前须提示
- authority：P，外部字段叠加E

### 投放.ad.url

- label：落地页
- control：URL输入
- required：网站目的地必填
- constraints：1至2048字符；HTTPS；无凭证；禁javascript/data
- default：空
- logic：服务端探测防SSRF；私网/元数据地址禁止
- authority：P，外部字段叠加E

### 投放.ad.url_tags

- label：追踪参数
- control：短输入
- required：否
- constraints：0至1024字符；key=value格式；不含?前缀
- default：空
- logic：不得写入Token或个人敏感信息
- authority：P，外部字段叠加E

### 投放.ad.cta

- label：行动按钮
- control：能力单选
- required：是
- constraints：目标/创意支持的CTA集合
- default：LEARN_MORE候选
- logic：不允许任意字符串
- authority：P，外部字段叠加E

### 投放.copies

- label：各层复制份数
- control：整数
- required：是
- constraints：1至50；非小数
- default：1
- logic：展开后最多10000广告/计划且各层最多10000节点
- authority：P，外部字段叠加E

### 投放.asset_ids

- label：素材池
- control：多选
- required：提交必填
- constraints：1至500份可用素材；单条广告首期只分配1份
- default：空
- logic：账户上传映射隔离；锁定版本
- authority：P，外部字段叠加E

### 投放.asset_type

- label：素材类型
- control：单选
- required：是
- constraints：ANY/IMAGE/VIDEO
- default：ANY
- logic：素材格式须符合目标与版位
- authority：P，外部字段叠加E

### 投放.execution_mode

- label：执行通道
- control：单选
- required：是
- constraints：META_API/ADSPOWER_UI
- default：META_API
- logic：UI通道默认禁用，能力验证后开启
- authority：P，外部字段叠加E

### 投放.activate_after_create

- label：创建后启用
- control：复选框
- required：是
- constraints：boolean
- default：false
- logic：额外publish权限、二次确认；执行独立命令
- authority：P，外部字段叠加E

### 模板.name

- label：模板名称
- control：短输入
- required：是
- constraints：1至80字符；同租户同所有者规范化唯一
- default：空
- logic：重名409，不自动覆盖
- authority：P，外部字段叠加E

### 模板.description

- label：模板说明
- control：长文本
- required：否
- constraints：0至500字符
- default：空
- logic：不保存凭据
- authority：P，外部字段叠加E

### 模板.visibility

- label：可见范围
- control：单选
- required：是
- constraints：PRIVATE/TEAM
- default：PRIVATE
- logic：TEAM需要模板共享权限
- authority：P，外部字段叠加E

### 规则.name

- label：规则名称
- control：短输入
- required：是
- constraints：1至80字符；租户内未归档名称唯一
- default：新建规则
- logic：trim后校验；不允许600字名称
- authority：P，外部字段叠加E

### 规则.target_level

- label：作用对象
- control：单选
- required：是
- constraints：CAMPAIGN/ADSET/AD
- default：AD
- logic：UI广告组映射ADSET；不得将旧GROUP写到Meta
- authority：P，外部字段叠加E

### 规则.scope_account_ids

- label：作用账户
- control：远程多选
- required：是
- constraints：1至50000个；使用范围引用，不传巨型URL
- default：当前授权选择
- logic：默认冻结授权范围；未来账户不自动加入
- authority：P，外部字段叠加E

### 规则.logic

- label：组间关系
- control：单选
- required：是
- constraints：AND/OR
- default：AND
- logic：采用三值逻辑，不用eval
- authority：P，外部字段叠加E

### 规则.groups

- label：条件组
- control：动态表单
- required：是
- constraints：1至5组；每组1至10条；总计<=20
- default：1组1条
- logic：空组拒绝；嵌套深度固定两层
- authority：P，外部字段叠加E

### 规则.metric

- label：指标
- control：单选
- required：是
- constraints：指标字典白名单
- default：spend
- logic：指标单位与归因profile展示
- authority：P，外部字段叠加E

### 规则.operator

- label：比较符
- control：单选
- required：是
- constraints：GT/GTE/LT/LTE/EQ/NEQ
- default：GTE
- logic：Decimal比较，不用二进制浮点等号
- authority：P，外部字段叠加E

### 规则.threshold

- label：指标阈值
- control：数字输入
- required：是
- constraints：非空；>=0；最多6位小数；计数指标整数
- default：无
- logic：CTR<=100；比率<=1000000；金额<=1000000000；空不转0
- authority：P，外部字段叠加E

### 规则.window

- label：观察窗口
- control：单选
- required：是
- constraints：TODAY/YESTERDAY/LAST_3D/LAST_7D
- default：LAST_3D
- logic：LAST含今天；低成熟度可能只给观察
- authority：P，外部字段叠加E

### 规则.frequency

- label：运行方式
- control：单选
- required：是
- constraints：INTERVAL/DAILY/WEEKLY
- default：INTERVAL
- logic：无每日运行起止窗口
- authority：P，外部字段叠加E

### 规则.interval_minutes

- label：间隔分钟
- control：整数
- required：INTERVAL必填
- constraints：15至1440
- default：30
- logic：不以页面定时器为调度源
- authority：P，外部字段叠加E

### 规则.time_of_day

- label：执行时刻
- control：时间输入
- required：DAILY/WEEKLY必填
- constraints：HH:mm，00:00至23:59
- default：10:00
- logic：不存在的DST时刻跳过并记日志；重复时刻仅一次
- authority：P，外部字段叠加E

### 规则.weekday

- label：星期
- control：单选
- required：WEEKLY必填
- constraints：1至7，周一至周日
- default：1
- logic：服务端统一，不混用JS星期0
- authority：P，外部字段叠加E

### 规则.timezone

- label：调度时区
- control：搜索单选
- required：是
- constraints：一个IANA时区<=64字符
- default：Asia/Shanghai
- logic：不是数据业务日时区；界面UTC±HH:mm并可带地区名，存IANA值，按参考日期处理夏令时
- authority：P，外部字段叠加E

### 规则.start_date

- label：生效日期
- control：日期
- required：是
- constraints：有效日期；<=end_date
- default：当天
- logic：执行须在日期范围内
- authority：P，外部字段叠加E

### 规则.end_date

- label：截止日期
- control：日期
- required：是
- constraints：>=start；跨度<=366天
- default：当天加90天
- logic：编辑后原模拟失效
- authority：P，外部字段叠加E

### 规则.cooldown_minutes

- label：分析冷却
- control：整数
- required：是
- constraints：0至10080
- default：60
- logic：按规则ID+对象原子限制，不限制纯评估
- authority：P，外部字段叠加E

### 规则.max_daily

- label：每日最多分析
- control：整数
- required：是
- constraints：1至1000
- default：5
- logic：按规则+对象+调度当地日；不按当前页面人数
- authority：P，外部字段叠加E

### 建议.action

- label：本次优化动作
- control：单选
- required：是
- constraints：BUDGET_SET/PAUSE/DELETE/OBSERVE
- default：AI结果
- logic：用户不能选择能力不支持动作
- authority：P，外部字段叠加E

### 建议.target_budget

- label：新预算
- control：金额输入
- required：BUDGET_SET必填
- constraints：预算字段规则；租户上下限；默认单次变化<=20%
- default：AI结果
- logic：改到真实预算拥有者；总预算需剩余花费约束
- authority：P，外部字段叠加E

### 建议.edit_reason

- label：修改建议原因
- control：长文本
- required：修改时必填
- constraints：1至1000字符
- default：空
- logic：原建议不可覆盖
- authority：P，外部字段叠加E

### 建议.delete_ack

- label：删除确认
- control：复选框
- required：DELETE必填
- constraints：必须true
- default：false
- logic：展示不可恢复性、子树数量及对象ID
- authority：P，外部字段叠加E

### 素材.name

- label：素材名称
- control：短输入
- required：是
- constraints：1至100字符
- default：文件名去扩展名
- logic：文件名不得作路径
- authority：P，外部字段叠加E

### 素材.file

- label：文件
- control：上传
- required：新建必填
- constraints：JPEG/PNG<=20MiB；MP4<=500MiB；每批<=50个
- default：无
- logic：产品限额；MIME与魔数一致；视频服务端处理；版位另校验
- authority：P，外部字段叠加E

### 素材.category_id

- label：分类
- control：单选
- required：是
- constraints：一个有效分类UUID
- default：未分类
- logic：未分类为系统固定项，不可删除
- authority：P，外部字段叠加E

### 素材.tags

- label：标签
- control：多选
- required：否
- constraints：0至20个启用标签
- default：空
- logic：停用标签保留旧关联，不可新增关联
- authority：P，外部字段叠加E

### 素材.tag_match

- label：标签关系
- control：单选
- required：是
- constraints：ALL/ANY
- default：ALL
- logic：没有标签时关系不影响结果
- authority：P，外部字段叠加E

### 素材.metric_range

- label：指标范围
- control：两个数字输入
- required：否
- constraints：可单边；非负；min<=max；最多6小数
- default：空
- logic：未知值不视为0；计数只允许整数
- authority：P，外部字段叠加E

### 素材.sort

- label：排序
- control：两个单选
- required：是
- constraints：spend/clicks/impressions/roas/conversions/usage/name + ASC/DESC
- default：spend DESC
- logic：null最后；ID作为稳定第二排序键
- authority：P，外部字段叠加E

### 标签分类.name

- label：标签或分类名称
- control：短输入
- required：是
- constraints：1至30字符；租户内同类唯一
- default：空
- logic：分类删除有引用时拒绝；标签可停用
- authority：P，外部字段叠加E

### 标签分类.group

- label：标签分组
- control：短输入
- required：否
- constraints：0至30字符
- default：空
- logic：仅组织标签，不参与Meta定向
- authority：P，外部字段叠加E

### 提醒.channels

- label：提醒渠道
- control：多选
- required：是
- constraints：首期仅IN_APP
- default：IN_APP
- logic：不默认发送邮件/短信
- authority：P，外部字段叠加E

### 提醒.snooze_minutes

- label：稍后提醒
- control：单选
- required：是
- constraints：15/60/240/1440
- default：60
- logic：到期恢复待处理；不改变任务状态
- authority：P，外部字段叠加E

### 环境.agent_name

- label：机器名称
- control：短输入
- required：是
- constraints：1至80字符
- default：空
- logic：租户内唯一
- authority：P，外部字段叠加E

### 环境.profile_id

- label：AdsPower Profile ID
- control：远程单选
- required：绑定必填
- constraints：1至128字符
- default：无
- logic：与agent_id构成绑定；不等于Meta账户ID
- authority：P，外部字段叠加E

### 环境.endpoint

- label：Local API地址
- control：受控配置
- required：是
- constraints：http://127.0.0.1或localhost加端口1至65535
- default：本机发现值
- logic：云端不得任意请求用户填的URL
- authority：P，外部字段叠加E

### 环境.probe_interval

- label：探测周期秒
- control：整数
- required：是
- constraints：10至300
- default：30
- logic：每机器限流器约束，按本机开放profile批量探测
- authority：P，外部字段叠加E

### 系统.display_name

- label：用户姓名
- control：短输入
- required：是
- constraints：1至50字符
- default：空
- logic：用户ID稳定，改名不覆盖历史操作快照
- authority：P，外部字段叠加E

### 系统.email

- label：登录邮箱
- control：邮箱
- required：邀请必填
- constraints：3至254字符；规范邮箱格式
- default：空
- logic：验证前不启用；不记录明文密码
- authority：P，外部字段叠加E

### 系统.roles

- label：角色
- control：多选
- required：是
- constraints：1至20个合法角色ID
- default：只读
- logic：修改需system.manage；不能自行提权
- authority：P，外部字段叠加E

### 系统.role_name

- label：角色名称
- control：短输入
- required：是
- constraints：1至50字符；租户内唯一
- default：空
- logic：内置角色保护，复制后自定义
- authority：P，外部字段叠加E

### 系统.permissions

- label：权限集合
- control：多选
- required：是
- constraints：0至服务端注册权限数；拒绝未知枚举
- default：空
- logic：菜单与动作、账户范围分别配置
- authority：P，外部字段叠加E

### 系统.secret_ref

- label：集成凭据引用
- control：服务端只写
- required：集成必填
- constraints：KMS/Vault引用1至255字符
- default：无
- logic：前端只显示掩码，禁止读取原token
- authority：P，外部字段叠加E

### 渠道.code

- label：渠道ID
- control：短输入
- required：是
- constraints：1至64字符；字母数字下划线短横线；同租户唯一
- default：空
- logic：trim；不作Meta对象ID
- authority：U字段；P约束/选项，生产外部数据受E约束

### 渠道.name

- label：渠道名称
- control：短输入
- required：否
- constraints：0至100字符
- default：回退渠道ID
- logic：用于系列命名及报表展示
- authority：U字段；P约束/选项，生产外部数据受E约束

### 渠道.product_id

- label：产品名称
- control：单选
- required：是
- constraints：一个有效产品ID
- default：无
- logic：被包绑定时禁止直接更换产品
- authority：U字段；P约束/选项，生产外部数据受E约束

### 渠道.agent_id

- label：总代
- control：单选
- required：是
- constraints：所属产品已选总代之一
- default：无
- logic：产品改变后重选
- authority：U字段；P约束/选项，生产外部数据受E约束

### 渠道.type

- label：类型
- control：单选
- required：是
- constraints：应用/网站/其他
- default：应用
- logic：与媒体字段独立
- authority：U字段；P约束/选项，生产外部数据受E约束

### 渠道.media

- label：媒体
- control：单选
- required：是
- constraints：Meta/Google/TikTok/其他
- default：Meta
- logic：当前投放原型仅Meta可选
- authority：U字段；P约束/选项，生产外部数据受E约束

### 渠道.url

- label：投放链接
- control：URL输入
- required：是
- constraints：1至2048字符；http/https；无凭据
- default：空
- logic：不自动覆盖广告落地页
- authority：U字段；P约束/选项，生产外部数据受E约束

### 渠道.status

- label：状态
- control：单选
- required：是
- constraints：启用/停用
- default：启用
- logic：停用后禁止新投放选择
- authority：U字段；P约束/选项，生产外部数据受E约束

### 户商导入.vendor_id

- label：所属户商
- control：单选
- required：是
- constraints：一个可管理户商ID
- default：二级页预选当前户商
- logic：批次受理后冻结
- authority：U字段；P约束/选项，生产外部数据受E约束

### 户商导入.account_ids_text

- label：账户ID列表
- control：长文本
- required：是
- constraints：1至20000字符；每批最多500项；数字ID1至32位，可带act_
- default：空
- logic：按字符串规范化、去重，逐项报错
- authority：U字段；P约束/选项，生产外部数据受E约束

### 户商导入.row_status

- label：导入状态
- control：只读
- required：是
- constraints：WAITING/FETCHING/SUCCEEDED/ALREADY_EXISTS/DUPLICATE/INVALID/FORBIDDEN/OWNERSHIP_CONFLICT/FAILED
- default：WAITING
- logic：失败重试只处理允许重试项
- authority：U字段；P约束/选项，生产外部数据受E约束

### 投放渠道.channel_id

- label：投放渠道
- control：单选
- required：提交必填
- constraints：一个启用且媒体为Meta的授权渠道
- default：无
- logic：变更后预检和素材分配失效
- authority：U字段；P约束/选项，生产外部数据受E约束

### 投放渠道.nickname_snapshot

- label：用户昵称快照
- control：只读
- required：是
- constraints：1至50字符；未配置回退姓名
- default：当前用户昵称/姓名
- logic：由服务端身份提供，不接收伪造actor
- authority：U字段；P约束/选项，生产外部数据受E约束

### 投放渠道.sequence

- label：系列自动编号
- control：只读
- required：是
- constraints：正整数，展示至少4位
- default：原子分配
- logic：展开后每系列独立；允许跳号，重试复用
- authority：U字段；P约束/选项，生产外部数据受E约束

### 投放渠道.naming_date

- label：命名年月日
- control：只读
- required：是
- constraints：YYYYMMDD；按Asia/Shanghai业务日期
- default：当前业务日
- logic：跨日重新预览，不改已提交任务
- authority：U字段；P约束/选项，生产外部数据受E约束

### 渠道报表.channel_id

- label：渠道筛选
- control：单选
- required：否
- constraints：有效渠道ID/UNASSIGNED/空
- default：全部
- logic：未归属渠道单列
- authority：U字段；P约束/选项，生产外部数据受E约束

### 渠道报表.operator_id

- label：投放师筛选
- control：单选
- required：否
- constraints：有数据权限的用户ID或空
- default：全部
- logic：服务端账户范围与筛选取交集
- authority：U字段；P约束/选项，生产外部数据受E约束


## 扩展字段

### 所有权.data_role

- constraints：USER/TEAM_ADMIN/SUPER_ADMIN；仅超级管理员授予
- default：USER
- authority：U01/U02

### 所有权.owner_user_id

- constraints：服务端默认本人；管理员可指定同目标团队用户
- default：当前用户
- authority：D v1.2

### 所有权.owner_team_id

- constraints：一个有效团队，服务端复验；不能自行扩scope
- default：当前团队
- authority：D v1.2

### 主数据.data_owner_user_ids

- constraints：1至500个同团队启用用户；更改需assign权限
- default：创建者
- authority：D v1.2

### 模板.recipient_user_ids

- constraints：0至500个显式接收者；TEAM需要share权限；不自动加入新成员
- default：空
- authority：D v1.2

### 投放.allow_repeat

- constraints：boolean；false要求素材数=广告数；true至少1份兼容素材
- default：false
- authority：D v1.2

### 投放.identity_bindings

- constraints：逐账户主页、逐组像素或应用、可选广告主页覆盖；提交时完整
- default：空
- authority：D v1.2

### 投放.profile_binding_ids

- constraints：ADSPOWER_UI逐账户必有有效绑定；API为空
- default：空
- authority：D v1.2

### 投放.workflow_version

- constraints：经能力验证的工作流版本
- default：能力包
- authority：D v1.2

### 投放.adapter_version

- constraints：经能力验证的页面/API适配器版本
- default：能力包
- authority：D v1.2

### 分配.algorithm_version

- constraints：allocation-v1；与seed/版本共同冻结
- default：allocation-v1
- authority：D v1.2

### 分配.seed

- constraints：0至2147483647整数；重新分配+1；重试不变
- default：0
- authority：D v1.2

### 反馈.configuration_state

- constraints：UNVERIFIED/VERIFIED/MISMATCH/UNKNOWN
- default：UNVERIFIED
- authority：D v1.2

### 反馈.delivery_state

- constraints：UNKNOWN/ACTIVE/PAUSED/REVIEWING/BLOCKED
- default：UNKNOWN
- authority：D v1.2

### 反馈.no_op

- constraints：boolean；已达目标仍须核验后才为true
- default：false
- authority：D v1.2

### 环境.profile_external_id

- constraints：1至128字符；与agent关联，不是广告账户ID
- default：无
- authority：D v1.2

### 环境.fencing_token

- constraints：正整数，服务端单调生成；不能由用户指定
- default：服务端生成
- authority：D v1.2

### 历史.attribution_version

- constraints：正整数，历史更正后新版本；旧快照保留
- default：1
- authority：D v1.2

### 权限.managed_team_ids

- constraints：TEAM_ADMIN显式管理团队集合
- default：[]
- authority：D

### 计划.account_scope_snapshot_id

- constraints：与非空account_ids互斥，引用冻结快照
- default：null
- authority：D

### 报表.granularity

- constraints：SUMMARY/DAY
- default：SUMMARY
- authority：D

### 手工操作.emergency_pause

- constraints：仅PAUSE且独立权限，不能绕过身份/锁/kill-switch
- default：false
- authority：D

