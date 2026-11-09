# Ant Design 前端架构与组件映射

## 1. 技术与交付
真实React + Ant Design组件，不是手写CSS仿AntD。精确版本见frontend/package-lock.json；Vite单文件构建，可离线打开。设计依据官方Getting Started及ConfigProvider文档：https://ant.design/docs/react/getting-started/ 、https://ant.design/components/config-provider 。

页面架构：ConfigProvider（中文语言与token）→App（message/modal上下文）→Layout→Header＋横向Menu（八模块）→Content→模块Tabs、Form、Table/列表→Modal/Drawer。顶部品牌ORBIT，主色靛蓝，白色顶栏和浅灰工作区；与旧白色侧栏导航区分。保留表格信息密度与左右滚动，不能为了“简洁”删列。

|原页面元素|Ant Design组件|保留约束|
|一级菜单|Layout.Header / Menu|仅八模块，角色可见性不扩权|
|子页/维度/层级|Tabs|原顺序、标题、数量徽标、状态保留|
|业务列表|Table|每列、单元格信息、操作、选择、横向滚动保留；原分页逻辑保留|
|字段组|Form.Item / Input / InputNumber / Select / Checkbox / Radio|原label、值、必填、禁用、约束；数值用stringMode避免精度改写|
|日期时间|当前原型Input date/time保留原输入语义；生产DatePicker/TimePicker|不改时区存储或业务日解释|
|详情编辑与确认|Modal / Drawer / Descriptions|原所有详情、动作及确认内容保留|
|提示与状态|Tag / Alert / message / Spin|原警告、未知、部分、错误与未授权不变|
|文件选择|Upload|桥接原文件输入与校验，不宣称真实安全扫描|
|布局|Card / Space / Divider|不合并不同币种或不同来源指标|

## 2. 原型迁移方式
本交付用**隔离的原业务状态适配器**保留原v2.17逻辑与数据，React读取其语义页面快照，把表格、控件、标签页、卡片、弹窗转换为真实Ant Design组件。事件回传原控件处理函数，保留表单联动、校验、权限与状态变化。隔离容器不向用户显示；可见工作区是Ant Design组件树。

这是原型迁移手段，旨在降低再次丢字段的风险；不是完成了生产前端重构。适配器中可能保留被退役流程的兼容代码与历史样本，但八模块白名单、权限和动作入口阻止进入对应业务。它们不构成新系统功能；生产构建必须按下面模块拆分，移除退役代码和旧依赖，不部署旧HTML业务引擎。

## 3. 生产目标架构
- app：ConfigProvider、认证上下文、路由白名单、布局与错误边界。
- features/accounts：完整账户Table、列配置、详情Drawer、OAuth、分配、批量添加。
- features/launch：原六区配置/差异树、身份绑定、分配预览、模板、任务、统计、失败提醒。
- features/monitor：原七Tab、AI建议与依据、批量确认、操作记录、采纳统计。
- features/rules：管理/编辑/模拟/触发与未来调度预览，不承载预设执行动作。
- features/assets：素材、分类、标签、指标筛选、批量删除。
- features/environments：机器/Profile/绑定/能力/租约/故障。
- features/channels：完整渠道表单和产品/总代引用选择。
- features/system：用户/团队/角色/菜单/字典/集成/审计。
- shared：Money、AccountTimezone、MetricQuality、EntityScopePicker、EvidenceDrawer、RevisionGuard、ReferenceDirectorySelect。Money格式化不参与金额运算，服务端Decimal是事实来源。

领域状态从API hooks获取，使用原OpenAPI DTO与后端状态机；不再用DOM作为状态事实来源。Table列定义与Form schema逐项映射字段字典，保留后端返回未知值，不默认补0。列表快照与建议冻结证据独立，ID用于关联而不是名称。

## 4. 响应与可访问性
桌面内容宽度随视口调整；多列表格本地横向滚动并保留固定标识/操作列，手机不删除字段。Menu溢出收纳，表单双列转单列。状态必须有文字；键盘焦点、Modal焦点圈与Select键盘行为依Ant Design实现。继承原HTML的个别布局仍需生产组件化时逐一审核，不将原型通过等同无障碍认证。

## 5. 字段验收
字段字典逐项深比较；原业务UI与AntD可见UI对比表头、字段标签、按钮和详情文本。差异仅允许删除边界清单中的动作、品牌替换和导航重组；任何其他缺失都属于回归，需修复或明确记录，不能以“页面精简”解释。
