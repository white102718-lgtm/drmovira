import type { ReportField, ReportRule } from './report-rules';

export interface DailyReportQuickTemplate {
  description: string;
  fields: Array<Omit<ReportField, 'id'>>;
  icon: string;
  name: string;
}

/**
 * 广告业务日报的常用起始模板。
 *
 * 模板只预置采集口径和填写节奏，人员范围仍需管理员按实际团队配置，
 * 避免将示例成员或权限范围错误地带入正式规则。
 */
export const dailyReportQuickTemplates: DailyReportQuickTemplate[] = [
  {
    description: '快速同步今日重点、完成情况、待协调事项与明日计划。',
    fields: [
      { label: '汇报日期', required: true, type: 'date' },
      { label: '今日工作总结', required: true, type: 'textarea' },
      { label: '完成成果 / 关键数据', required: false, type: 'textarea' },
      { label: '问题与需协调事项', required: false, type: 'textarea' },
      { label: '明日工作计划', required: true, type: 'textarea' },
    ],
    icon: 'calendar-days',
    name: '工作日报',
  },
  {
    description: '按项目和媒体追踪消耗、转化及当天优化动作。',
    fields: [
      { label: '汇报日期', required: true, type: 'date' },
      { label: '项目名称', required: true, type: 'text' },
      {
        label: '投放平台',
        options: ['Facebook', 'Google', 'TikTok', '其他'],
        required: true,
        type: 'single-select',
      },
      { label: '广告账户 / 渠道号', required: true, type: 'text' },
      { label: '当日消耗', required: true, type: 'number' },
      { label: '展示量', required: false, type: 'number' },
      { label: '点击量', required: false, type: 'number' },
      { label: '注册 / 安装量', required: false, type: 'number' },
      { label: '首购 / 转化数', required: false, type: 'number' },
      { label: '今日优化动作与结论', required: true, type: 'textarea' },
      { label: '异常与风险', required: false, type: 'textarea' },
      { label: '明日投放计划', required: true, type: 'textarea' },
    ],
    icon: 'chart-no-axes-combined',
    name: '媒体投放优化日报',
  },
  {
    description: '沉淀素材产出、上线表现和下一轮迭代方向。',
    fields: [
      { label: '汇报日期', required: true, type: 'date' },
      { label: '项目名称', required: true, type: 'text' },
      {
        label: '投放平台',
        options: ['Facebook', 'Google', 'TikTok', '其他'],
        required: true,
        type: 'single-select',
      },
      { label: '新增素材数量', required: true, type: 'number' },
      { label: '上线素材数量', required: true, type: 'number' },
      { label: '表现达标素材数量', required: false, type: 'number' },
      { label: '素材方向与测试结论', required: true, type: 'textarea' },
      { label: '待优化素材及原因', required: false, type: 'textarea' },
      { label: '明日制作与测试计划', required: true, type: 'textarea' },
    ],
    icon: 'palette',
    name: '素材产出日报',
  },
  {
    description: '集中记录账户受限、审核拒登和预算异常的处理进度。',
    fields: [
      { label: '发现日期', required: true, type: 'date' },
      { label: '项目名称', required: true, type: 'text' },
      {
        label: '投放平台',
        options: ['Facebook', 'Google', 'TikTok', '其他'],
        required: true,
        type: 'single-select',
      },
      { label: '广告账户 / 渠道号', required: true, type: 'text' },
      {
        label: '异常类型',
        options: [
          '账户受限',
          '广告审核拒登',
          '支付 / 余额异常',
          '预算异常',
          '数据异常',
          '其他',
        ],
        required: true,
        type: 'single-select',
      },
      {
        label: '影响程度',
        options: ['低：不影响投放', '中：部分受影响', '高：投放中断'],
        required: true,
        type: 'single-select',
      },
      { label: '问题描述', required: true, type: 'textarea' },
      { label: '已采取措施', required: true, type: 'textarea' },
      {
        label: '当前处理状态',
        options: ['待处理', '处理中', '已恢复', '需协同'],
        required: true,
        type: 'single-select',
      },
      { label: '需要协同事项', required: false, type: 'textarea' },
    ],
    icon: 'shield-alert',
    name: '账户异常巡检日报',
  },
  {
    description: '同步项目目标、交付状态、客户反馈与需协调事项。',
    fields: [
      { label: '汇报日期', required: true, type: 'date' },
      { label: '项目名称', required: true, type: 'text' },
      { label: '今日目标与完成情况', required: true, type: 'textarea' },
      { label: '投放 / 交付关键数据', required: false, type: 'textarea' },
      { label: '客户反馈与处理进度', required: false, type: 'textarea' },
      { label: '风险与需协调事项', required: false, type: 'textarea' },
      { label: '明日计划', required: true, type: 'textarea' },
    ],
    icon: 'folders',
    name: '项目运营协同日报',
  },
];

/** 将业务模板转换为独立规则，保证多次使用模板时字段不会共享引用。 */
export function createRuleFromDailyReportTemplate(
  template: DailyReportQuickTemplate,
  baseRule: ReportRule,
): ReportRule {
  const timestamp = Date.now();

  return {
    ...baseRule,
    deadline: '',
    fields: template.fields.map((field, index) => ({
      ...field,
      id: `template-${timestamp}-${index + 1}`,
      options: field.options ? [...field.options] : undefined,
    })),
    icon: template.icon,
    id: `rule-${timestamp}`,
    name: template.name,
    period: '每天',
    reminderEnabled: true,
    schedule: {
      ...baseRule.schedule,
      deadlineTime: baseRule.schedule.deadlineTime,
      reminderTime: baseRule.schedule.reminderTime,
      startTime: '00:00',
      submissionDays: [1, 2, 3, 4, 5, 6, 7],
    },
  };
}
