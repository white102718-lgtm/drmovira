export type ReportFieldType =
  | 'date'
  | 'image'
  | 'multi-select'
  | 'number'
  | 'single-select'
  | 'text'
  | 'textarea'
  | 'upload';

export interface ReportField {
  id: string;
  label: string;
  /** 单选、多选字段的可选值，配置顺序即填写页展示顺序。 */
  options?: string[];
  required: boolean;
  type: ReportFieldType;
}

export interface ReportRuleMember {
  id: string;
  label: string;
  type: 'department' | 'role' | 'user';
}

export interface ReportRulePersonnel {
  cc: ReportRuleMember[];
  reporters: ReportRuleMember[];
  viewers: ReportRuleMember[];
  viewerScope: 'all' | 'custom';
  writers: ReportRuleMember[];
}

/** 服务端以 IANA 时区执行日报周期、截止和提醒；不再只是页面展示配置。 */
export interface ReportRuleSchedule {
  deadlineTime: string;
  reminderTime: string;
  startTime: string;
  submissionDayOfMonth?: number;
  submissionDays: number[];
  timezone: string;
}

export interface ReportRule {
  /** 当前用户是否在填写人员范围内；仅由日报可见规则接口返回。 */
  canWrite?: boolean;
  deadline: string;
  fields: ReportField[];
  id: string;
  icon: string;
  name: string;
  /** 普通日报配置保留消息展示设置；日报提交固定同时发送站内消息与飞书。 */
  notificationChannels: {
    feishu: boolean;
    system: boolean;
  };
  personnel: ReportRulePersonnel;
  period: '每天' | '每周' | '每双周' | '每月' | '不重复';
  reminderEnabled: boolean;
  schedule: ReportRuleSchedule;
  submitNotice: boolean;
  ccNotice: boolean;
}

export interface MonthlyReport {
  attachments?: Record<string, ReportAttachment[]>;
  author: string;
  /** 服务端提交人 ID；按人查看必须优先使用它，避免同名人员串数据。 */
  authorId?: string;
  createdAt: string;
  fields: Record<string, string>;
  id: string;
  ruleId: string;
  /**
   * 提交时固化的规则快照。规则后续被修改或删除时，历史日报仍可还原当时的
   * 汇报名称、周期、截止时间和字段定义，保证记录可追溯。
   */
  ruleSnapshot?: ReportRuleSnapshot;
}

export interface ReportAttachment {
  id: string;
  name: string;
}

export interface ReportRuleSnapshot {
  deadline: string;
  fields: ReportField[];
  name: string;
  period: ReportRule['period'];
}

export const REPORT_RULES_UPDATED_EVENT = 'fusion:report-rules-updated';
const RULES_KEY = 'fusion:report-rules:v1';
const REPORTS_KEY = 'fusion:monthly-reports:v1';

const defaultRule: ReportRule = {
  ccNotice: true,
  deadline: '23:00 (Asia/Shanghai)',
  fields: [
    {
      id: 'monthly-target',
      label: '本月目标',
      required: true,
      type: 'textarea',
    },
    {
      id: 'progress-sync',
      label: '进展同步',
      required: true,
      type: 'textarea',
    },
    {
      id: 'next-month-plan',
      label: '下月计划',
      required: true,
      type: 'textarea',
    },
    {
      id: 'review-summary',
      label: '复盘总结',
      required: false,
      type: 'textarea',
    },
  ],
  icon: '31',
  id: 'monthly-report',
  name: '工作月报',
  notificationChannels: {
    feishu: true,
    system: true,
  },
  personnel: {
    cc: [],
    reporters: [],
    viewers: [],
    viewerScope: 'custom',
    writers: [],
  },
  period: '每月',
  reminderEnabled: true,
  schedule: {
    deadlineTime: '23:00',
    reminderTime: '19:00',
    startTime: '00:00',
    submissionDayOfMonth: 1,
    submissionDays: [],
    timezone: 'Asia/Shanghai',
  },
  submitNotice: true,
};

function clonePersonnel(
  personnel?: Partial<ReportRulePersonnel>,
): ReportRulePersonnel {
  return {
    cc: (personnel?.cc ?? []).map((member) => ({ ...member })),
    reporters: (personnel?.reporters ?? []).map((member) => ({ ...member })),
    viewers: (personnel?.viewers ?? []).map((member) => ({ ...member })),
    viewerScope: personnel?.viewerScope === 'all' ? 'all' : 'custom',
    writers: (personnel?.writers ?? []).map((member) => ({ ...member })),
  };
}

function cloneRule(rule: ReportRule): ReportRule {
  return {
    ...rule,
    fields: rule.fields.map((field) => ({
      ...field,
      options: field.options?.map((option) => option.trim()).filter(Boolean),
    })),
    notificationChannels: {
      feishu: rule.notificationChannels?.feishu !== false,
      system: rule.notificationChannels?.system !== false,
    },
    personnel: clonePersonnel(rule.personnel),
    schedule: {
      ...defaultRule.schedule,
      ...rule.schedule,
      submissionDays: [...(rule.schedule?.submissionDays ?? defaultRule.schedule.submissionDays)],
    },
  };
}

function parseRules(value: string | null): ReportRule[] {
  if (!value) return [cloneRule(defaultRule)];
  try {
    const parsed = JSON.parse(value);
    // 空数组表示管理员已主动删除全部规则，不能在下次读取时重新生成默认规则。
    if (!Array.isArray(parsed)) return [cloneRule(defaultRule)];
    return parsed.map((rule) => ({
      ...cloneRule(defaultRule),
      ...rule,
      fields: Array.isArray(rule.fields)
        ? rule.fields
        : cloneRule(defaultRule).fields,
      personnel: clonePersonnel(rule.personnel),
      notificationChannels: {
        feishu: rule.notificationChannels?.feishu !== false,
        system: rule.notificationChannels?.system !== false,
      },
      schedule: {
        ...cloneRule(defaultRule).schedule,
        ...(rule.schedule ?? {}),
        submissionDays: Array.isArray(rule.schedule?.submissionDays)
          ? rule.schedule.submissionDays
          : cloneRule(defaultRule).schedule.submissionDays,
      },
    }));
  } catch {
    return [cloneRule(defaultRule)];
  }
}

export function getDefaultReportRule() {
  return cloneRule(defaultRule);
}

export function loadReportRules(): ReportRule[] {
  if (typeof window === 'undefined') return [cloneRule(defaultRule)];
  return parseRules(window.localStorage.getItem(RULES_KEY));
}

export function saveReportRules(rules: ReportRule[]) {
  const value = rules.map(cloneRule);
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(RULES_KEY, JSON.stringify(value));
    window.dispatchEvent(new CustomEvent(REPORT_RULES_UPDATED_EVENT));
  }
  return value;
}

export function loadMonthlyReports(): MonthlyReport[] {
  if (typeof window === 'undefined') return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(REPORTS_KEY) ?? '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveMonthlyReports(reports: MonthlyReport[]) {
  if (typeof window !== 'undefined')
    window.localStorage.setItem(REPORTS_KEY, JSON.stringify(reports));
}
