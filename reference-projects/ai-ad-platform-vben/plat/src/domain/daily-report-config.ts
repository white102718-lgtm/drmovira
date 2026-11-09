export type DailyReportFieldKey =
  | 'actualSpend'
  | 'adjustmentAmount'
  | 'adjustmentType'
  | 'channelCode'
  | 'clicks'
  | 'dailySpend'
  | 'date'
  | 'firstPurchase'
  | 'impressions'
  | 'inAccountInstalls'
  | 'inAccountRegistrations'
  | 'platform'
  | 'projectName'
  | 'remark'
  | 'reporterName'
  | 'returnSpend'
  | 'returnSpendIncrease'
  | 'secondaryDeduction';

export type DailyReportFieldInputType =
  | 'date'
  | 'number'
  | 'platform'
  | 'project'
  | 'select'
  | 'text'
  | 'textarea';

export interface DailyReportFieldConfig {
  /** The field can be entered by the reporter rather than supplied by the system. */
  editable: boolean;
  enabled: boolean;
  inputType: DailyReportFieldInputType;
  key: DailyReportFieldKey;
  label: string;
  order: number;
  required: boolean;
}

export const DAILY_REPORT_FIELD_CONFIG_STORAGE_KEY =
  'fusion:daily-report-field-config:v1';

export const DAILY_REPORT_CONFIG_UPDATED_EVENT =
  'fusion:daily-report-config-updated';

const defaultDailyReportFields: DailyReportFieldConfig[] = [
  {
    editable: true,
    enabled: true,
    inputType: 'date',
    key: 'date',
    label: '日期',
    order: 10,
    required: true,
  },
  {
    editable: false,
    enabled: true,
    inputType: 'text',
    key: 'reporterName',
    label: '姓名辅助列',
    order: 20,
    required: true,
  },
  {
    editable: true,
    enabled: true,
    inputType: 'project',
    key: 'projectName',
    label: '项目名称',
    order: 30,
    required: true,
  },
  {
    editable: true,
    enabled: true,
    inputType: 'text',
    key: 'channelCode',
    label: '渠道号',
    order: 40,
    required: true,
  },
  {
    editable: true,
    enabled: true,
    inputType: 'platform',
    key: 'platform',
    label: '平台',
    order: 50,
    required: true,
  },
  {
    editable: true,
    enabled: true,
    inputType: 'number',
    key: 'dailySpend',
    label: '日报消耗',
    order: 60,
    required: true,
  },
  {
    editable: true,
    enabled: true,
    inputType: 'number',
    key: 'impressions',
    label: '展示',
    order: 70,
    required: false,
  },
  {
    editable: true,
    enabled: true,
    inputType: 'number',
    key: 'clicks',
    label: '点击',
    order: 80,
    required: false,
  },
  {
    editable: true,
    enabled: true,
    inputType: 'number',
    key: 'inAccountInstalls',
    label: '账户内安装',
    order: 90,
    required: false,
  },
  {
    editable: true,
    enabled: true,
    inputType: 'number',
    key: 'inAccountRegistrations',
    label: '账户内注册',
    order: 100,
    required: false,
  },
  {
    editable: true,
    enabled: true,
    inputType: 'number',
    key: 'firstPurchase',
    label: '账户内首购',
    order: 110,
    required: false,
  },
  {
    editable: true,
    enabled: true,
    inputType: 'number',
    key: 'adjustmentAmount',
    label: '调整金额',
    order: 120,
    required: false,
  },
  {
    editable: true,
    enabled: true,
    inputType: 'number',
    key: 'secondaryDeduction',
    label: '二次核减',
    order: 130,
    required: false,
  },
  {
    editable: true,
    enabled: true,
    inputType: 'select',
    key: 'adjustmentType',
    label: '调整额类型',
    order: 140,
    required: false,
  },
  {
    editable: true,
    enabled: true,
    inputType: 'number',
    key: 'returnSpend',
    label: '含回流消耗',
    order: 150,
    required: false,
  },
  {
    editable: true,
    enabled: true,
    inputType: 'number',
    key: 'actualSpend',
    label: '实际消耗',
    order: 160,
    required: false,
  },
  {
    editable: true,
    enabled: true,
    inputType: 'number',
    key: 'returnSpendIncrease',
    label: '回流增加额',
    order: 170,
    required: false,
  },
  {
    editable: true,
    enabled: true,
    inputType: 'textarea',
    key: 'remark',
    label: '备注',
    order: 180,
    required: false,
  },
];

function cloneDefaultFields(): DailyReportFieldConfig[] {
  return defaultDailyReportFields.map((field) => ({ ...field }));
}

function normalizeDailyReportFields(
  candidate: unknown,
): DailyReportFieldConfig[] {
  if (!Array.isArray(candidate)) return cloneDefaultFields();

  const savedByKey = new Map(
    candidate
      .filter(
        (item): item is Partial<DailyReportFieldConfig> & { key: string } =>
          Boolean(item) && typeof item === 'object' && 'key' in item,
      )
      .map((item) => [item.key, item]),
  );

  return cloneDefaultFields()
    .map((field) => {
      const saved = savedByKey.get(field.key);
      if (!saved) return field;

      return {
        ...field,
        enabled:
          typeof saved.enabled === 'boolean' ? saved.enabled : field.enabled,
        order:
          typeof saved.order === 'number' && Number.isFinite(saved.order)
            ? saved.order
            : field.order,
        required:
          typeof saved.required === 'boolean' ? saved.required : field.required,
      };
    })
    .sort((left, right) => left.order - right.order);
}

export function getDefaultDailyReportFields(): DailyReportFieldConfig[] {
  return cloneDefaultFields();
}

export function loadDailyReportFields(): DailyReportFieldConfig[] {
  if (typeof window === 'undefined') return cloneDefaultFields();

  try {
    return normalizeDailyReportFields(
      JSON.parse(
        window.localStorage.getItem(DAILY_REPORT_FIELD_CONFIG_STORAGE_KEY) ??
          '[]',
      ),
    );
  } catch {
    return cloneDefaultFields();
  }
}

export function saveDailyReportFields(
  fields: DailyReportFieldConfig[],
): DailyReportFieldConfig[] {
  const normalized = normalizeDailyReportFields(fields);
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(
      DAILY_REPORT_FIELD_CONFIG_STORAGE_KEY,
      JSON.stringify(normalized),
    );
    window.dispatchEvent(new CustomEvent(DAILY_REPORT_CONFIG_UPDATED_EVENT));
  }
  return normalized;
}
