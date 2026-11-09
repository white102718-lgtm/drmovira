import type { ReportRule } from './report-rules';

import { getDefaultReportRule } from './report-rules';

/** 前端固定表单对应的稳定规则标识，不能被普通日报配置替代。 */
export const DELIVERY_DAILY_REPORT_ID = 'delivery-daily-report';
/** 绩效报表基于投放日报汇总展示，配置仅维护人员范围、周期与提醒。 */
export const PERFORMANCE_REPORT_ID = 'performance-report';
/** 历史规则 ID 含 daily-report；为兼容已落库规则和历史提交，不可改名。 */
export const MATERIAL_DESIGNER_DAILY_REPORT_ID =
  'material-designer-daily-report';

const fixedDailyReportRuleDefinitions = [
  {
    icon: 'bar-chart-3',
    id: DELIVERY_DAILY_REPORT_ID,
    name: '投放日报',
    period: '每天',
  },
  {
    icon: 'bar-chart-3',
    id: PERFORMANCE_REPORT_ID,
    name: '绩效报表',
    period: '每天',
  },
  {
    icon: 'palette',
    id: MATERIAL_DESIGNER_DAILY_REPORT_ID,
    name: '素材师月报',
    period: '每月',
  },
] as const;

/** 判断规则是否由固定日报表单使用。 */
export function isFixedDailyReportRule(ruleId: string) {
  return fixedDailyReportRuleDefinitions.some((rule) => rule.id === ruleId);
}

/** 素材师月报保留旧规则 ID，但业务周期固定为每月。 */
export function isMaterialDesignerMonthlyReportRule(ruleId: string) {
  return ruleId === MATERIAL_DESIGNER_DAILY_REPORT_ID;
}

/**
 * 固定日报只在这里配置人员、周期、提醒等通用规则；实际填写字段由业务页面维护。
 */
export function getFixedDailyReportRules(): ReportRule[] {
  return fixedDailyReportRuleDefinitions.map((definition) => {
    const defaultRule = getDefaultReportRule();

    return {
      ...defaultRule,
      fields: [],
      icon: definition.icon,
      id: definition.id,
      name: definition.name,
      period: definition.period,
      schedule: {
        ...defaultRule.schedule,
        submissionDays: [],
      },
    };
  });
}

/**
 * 固定日报始终显示并强制清空低代码字段，防止服务端历史数据重新开放字段编辑。
 */
export function mergeFixedDailyReportRules(rules: ReportRule[]): ReportRule[] {
  const fixedRules = getFixedDailyReportRules().map((defaultRule) => {
    const persistedRule = rules.find((rule) => rule.id === defaultRule.id);
    const isMaterialMonthlyReport = isMaterialDesignerMonthlyReportRule(
      defaultRule.id,
    );
    const persistedSubmissionDay =
      persistedRule?.schedule?.submissionDayOfMonth;
    const submissionDayOfMonth =
      typeof persistedSubmissionDay === 'number' &&
      persistedSubmissionDay >= 1 &&
      persistedSubmissionDay <= 28
        ? persistedSubmissionDay
        : 1;

    return {
      ...defaultRule,
      ...persistedRule,
      fields: [],
      icon: defaultRule.icon,
      id: defaultRule.id,
      name: defaultRule.name,
      period: isMaterialMonthlyReport
        ? defaultRule.period
        : (persistedRule?.period ?? defaultRule.period),
      personnel: {
        ...defaultRule.personnel,
        ...persistedRule?.personnel,
      },
      schedule: {
        ...defaultRule.schedule,
        ...persistedRule?.schedule,
        ...(isMaterialMonthlyReport
          ? {
              submissionDayOfMonth,
              submissionDays: [],
            }
          : {}),
      },
    };
  });

  return [
    ...fixedRules,
    ...rules.filter((rule) => !isFixedDailyReportRule(rule.id)),
  ];
}
