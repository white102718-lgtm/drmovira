import type { DynamicFormField } from '#/api/asset-flow';

/** 固定汇报申请编码；仅审批流可配置，填写字段始终由业务代码维护。 */
export const DELIVERY_DAILY_REPORT_APPLICATION_CODE = 'DELIVERY_DAILY_REPORT';

export type FixedDailyReportApplicationCode =
  typeof DELIVERY_DAILY_REPORT_APPLICATION_CODE;

export interface FixedDailyReportApplicationDefinition {
  code: FixedDailyReportApplicationCode;
  description: string;
  icon: string;
  name: string;
}

/** 仅用于审批配置的固定表单说明，运行时不使用低代码表单渲染。 */
export const fixedDailyReportApplicationDefinitions: FixedDailyReportApplicationDefinition[] =
  [
    {
      code: DELIVERY_DAILY_REPORT_APPLICATION_CODE,
      description: '按任务线批量填写投放日报，并提交至已配置的审批流程。',
      icon: 'lucide:chart-no-axes-combined',
      name: '投放日报申请',
    },
  ];

const fixedCodes = new Set<FixedDailyReportApplicationCode>(
  fixedDailyReportApplicationDefinitions.map((item) => item.code),
);

/** 判断审批配置是否属于业务固定日报，避免错误开放低代码字段编辑。 */
export function isFixedDailyReportApplication(
  value: string | undefined,
): value is FixedDailyReportApplicationCode {
  return Boolean(
    value && fixedCodes.has(value as FixedDailyReportApplicationCode),
  );
}

/**
 * 固定汇报申请不允许低代码配置字段；此快照仅用于审批详情回显字段名。
 * 实际录入、校验与计算全部在固定汇报申请页面完成。
 */
export const fixedDailyReportPreviewSchemas: Record<
  FixedDailyReportApplicationCode,
  DynamicFormField[]
> = {
  [DELIVERY_DAILY_REPORT_APPLICATION_CODE]: [
    {
      key: 'rows',
      label: '投放日报明细',
      required: true,
      type: 'textarea',
      width: 'full',
    },
  ],
};
