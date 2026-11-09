import type {
  PlatformCode,
  ProjectKpiRequirement,
  ProjectListParams,
  ProjectOption,
  ProjectPriority,
  ProjectStatus,
  ProjectSummary,
} from '#/api/fusion/types';

export interface MpowerTaskKpi {
  calculationField?: string;
  calculationSymbol?: string;
  computeParams?: number | string;
  computeParams2?: number | string;
  maxNum?: number | string;
  minNum?: number | string;
}

export interface MpowerTask {
  am?: string;
  createTime?: string;
  dataSpecialist?: string;
  endTime?: string;
  kpi?: string;
  liabilityCompany?: string;
  mediaPlacement?: string;
  outsourcingFlag?: number | string;
  outsourcingTeam?: string;
  priority?: number | string;
  productInfo?: string;
  region?: string;
  reportLink?: string;
  serviceFee?: string;
  startTime?: string;
  taskId: string;
  taskKpiInfos?: MpowerTaskKpi[];
  taskName?: string;
  taskNo?: string;
  taskStatus?: number | string;
  updateTime?: string;
}

export interface MpowerTaskListQuery {
  pageNum: number;
  pageSize: number;
  taskName?: string;
  taskStatus?: number;
}

const platformAliases: Record<string, PlatformCode> = {
  facebook: 'facebook',
  fb: 'facebook',
  google: 'google',
  tiktok: 'tiktok',
  'tik tok': 'tiktok',
};

const statusToMpower: Partial<Record<ProjectStatus, number>> = {
  active: 1,
  archived: 3,
  draft: 0,
  ended: 3,
  paused: 2,
  pending: 0,
};

function asFiniteNumber(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function parseJsonStringArray(value?: string): string[] {
  if (!value?.trim()) return [];
  try {
    const parsed = JSON.parse(value);
    if (Array.isArray(parsed)) {
      return parsed.map(String).filter(Boolean);
    }
  } catch {
    // 兼容旧数据中的逗号分隔地区。
  }
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function mapPlatforms(value?: string): PlatformCode[] {
  if (!value) return [];
  return value
    .split(/[,/]/)
    .map((item) => platformAliases[item.trim().toLowerCase()])
    .filter((item): item is PlatformCode => Boolean(item));
}

function mapPriority(value: unknown): ProjectPriority {
  if (String(value) === '1') return 'high';
  if (String(value) === '3') return 'low';
  return 'normal';
}

function mapStatus(value: unknown): ProjectStatus {
  switch (String(value)) {
    case '1':
      return 'active';
    case '2':
      return 'paused';
    case '3':
    case '4':
    case '5':
      return 'ended';
    default:
      return 'pending';
  }
}

function mapKpiRequirements(items?: MpowerTaskKpi[]): ProjectKpiRequirement[] {
  return (items ?? []).flatMap((item) => {
    const metricAliases: Record<string, ProjectKpiRequirement['metric']> = {
      cpa: 'CPA',
      costPerPurchase: 'CPA',
      costPerUniquePurchase: 'CPP',
      roasPurchase: 'ROAS',
    };
    const metric = metricAliases[item.calculationField?.trim() ?? ''];
    if (!metric) return [];
    const symbol = item.calculationSymbol;
    const comparatorAliases: Record<
      string,
      ProjectKpiRequirement['comparator']
    > = {
      '1': '>',
      '2': '<',
      '3': '=',
      '4': '>=',
      '5': '<=',
      '6': 'between',
      '<': '<',
      '<=': '<=',
      '=': '=',
      '>': '>',
      '>=': '>=',
      between: 'between',
    };
    const comparator = comparatorAliases[symbol ?? ''] ?? '>=';
    const target = asFiniteNumber(
      item.computeParams ?? item.minNum ?? item.maxNum,
    );
    return [
      {
        comparator,
        metric,
        target,
        targetMax:
          comparator === 'between'
            ? asFiniteNumber(item.computeParams2 ?? item.maxNum, target)
            : undefined,
      },
    ];
  });
}

export function mapMpowerTask(task: MpowerTask): ProjectSummary {
  const kpiRequirements = mapKpiRequirements(task.taskKpiInfos);
  return {
    adAccountCount: 0,
    amName: task.am || undefined,
    attributionWindow: '',
    countryRegions: parseJsonStringArray(task.region),
    currency: 'USD',
    customerDailyReportUrl: task.reportLink || undefined,
    dailyBudget: 0,
    dataSpecialist: task.dataSpecialist || undefined,
    deliveryLines: [],
    endDate: task.endTime || undefined,
    id: String(task.taskId),
    isOutsourced: String(task.outsourcingFlag) === '1',
    kpiRequirements,
    materialCount: 0,
    name: task.taskName ?? '',
    platforms: mapPlatforms(task.mediaPlacement),
    primaryKpi: kpiRequirements[0]?.metric ?? task.kpi ?? '',
    priority: mapPriority(task.priority),
    productInfo: task.productInfo || undefined,
    productName: '',
    projectCode: task.taskNo ?? '',
    responsibleTeam: task.liabilityCompany || undefined,
    serviceFeePercent: asFiniteNumber(task.serviceFee?.split('/')[0]),
    startDate: task.startTime ?? '',
    status: mapStatus(task.taskStatus),
    timezone: '',
    updatedAt: task.updateTime ?? task.createTime ?? '',
  };
}

export function mapMpowerTaskOption(option: {
  name?: string;
  value?: bigint | number | string;
}): ProjectOption {
  return {
    deliveryLines: [],
    id: String(option.value ?? ''),
    name: option.name ?? '',
    productName: '',
    status: 'pending',
  };
}

export function mapProjectListQuery(
  query: ProjectListParams = {},
): MpowerTaskListQuery {
  if (query.customerId) {
    throw new Error('旧项目接口不支持按客户筛选');
  }
  if (query.platform) {
    throw new Error('旧项目接口不支持按投放平台筛选');
  }
  return {
    pageNum: query.page ?? 1,
    pageSize: query.pageSize ?? 20,
    taskName: query.keyword?.trim() || undefined,
    taskStatus: query.status ? statusToMpower[query.status] : undefined,
  };
}
