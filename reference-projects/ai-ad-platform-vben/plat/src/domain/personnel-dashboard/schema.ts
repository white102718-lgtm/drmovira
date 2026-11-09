import type {
  PersonnelDashboardCategory,
  PersonnelDashboardDataType,
  PersonnelDashboardField,
  PersonnelDashboardSchema,
} from './types';

interface FieldOptions {
  emptyText?: string;
  filterable?: boolean;
  fixed?: 'left' | 'right';
  sortable?: boolean;
  sourceKey?: string;
  summarizable?: boolean;
}

function field(
  key: string,
  label: string,
  dataType: PersonnelDashboardDataType,
  width: number,
  options: FieldOptions = {},
): PersonnelDashboardField {
  return {
    dataType,
    emptyText: options.emptyText ?? '—',
    filterable: options.filterable ?? ['status', 'text'].includes(dataType),
    fixed: options.fixed,
    key,
    label,
    sortable: options.sortable ?? true,
    sourceKey: options.sourceKey ?? label,
    summarizable: options.summarizable ?? false,
    width,
  };
}

function createDeliveryPersonnelFields(): PersonnelDashboardField[] {
  return [
    field('name', '投手姓名', 'text', 156, {
      fixed: 'left',
      sourceKey: '投手姓名',
    }),
    field('spend', '消耗', 'currency', 124, {
      sourceKey: '消耗',
      summarizable: true,
    }),
    field('accountId', '账户ID', 'text', 176, { sourceKey: '账户ID' }),
    field('accountType', '户的类型', 'text', 238, { sourceKey: '户的类型' }),
    field('projectName', '项目', 'text', 164, { sourceKey: '项目' }),
    field('runningCampaign', '在跑系列', 'text', 126, {
      sourceKey: '在跑系列',
    }),
  ];
}

export const personnelDashboardSchemas: Record<
  PersonnelDashboardCategory,
  PersonnelDashboardSchema
> = {
  gamePlatform: {
    category: 'gamePlatform',
    fields: createDeliveryPersonnelFields(),
    label: '项目',
    legacyTabKey: 'game_platform',
    sheetName: '项目',
  },
  agencyLine: {
    category: 'agencyLine',
    fields: createDeliveryPersonnelFields(),
    label: '户的类型',
    legacyTabKey: 'agent_line',
    sheetName: '户的类型',
  },
  placer: {
    category: 'placer',
    fields: createDeliveryPersonnelFields(),
    label: '投手姓名',
    legacyTabKey: 'placer_id',
    sheetName: '投手姓名',
  },
  account: {
    category: 'account',
    fields: createDeliveryPersonnelFields(),
    label: '账户ID',
    legacyTabKey: 'account_id',
    sheetName: '账户ID',
  },
  runningSeries: {
    category: 'runningSeries',
    fields: createDeliveryPersonnelFields(),
    label: '在跑系列',
    legacyTabKey: 'running_series',
    sheetName: '在跑系列',
  },
};

const legacyCategoryAliases: Record<string, PersonnelDashboardCategory> = {
  account: 'account',
  account_id: 'account',
  agencyLine: 'agencyLine',
  agent_line: 'agencyLine',
  game: 'gamePlatform',
  game_platform: 'gamePlatform',
  gamePlatform: 'gamePlatform',
  personnel: 'placer',
  placer: 'placer',
  placer_id: 'placer',
  runningSeries: 'runningSeries',
  running_series: 'runningSeries',
};

export const personnelDashboardCategoryOrder: PersonnelDashboardCategory[] = [
  'placer',
  'account',
  'agencyLine',
  'gamePlatform',
  'runningSeries',
];

export function resolvePersonnelDashboardCategory(value?: null | string) {
  return value ? legacyCategoryAliases[value] : undefined;
}

export function getPersonnelDashboardSchema(
  category: PersonnelDashboardCategory,
) {
  return personnelDashboardSchemas[category];
}
