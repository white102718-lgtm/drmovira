import type { HomeOverviewAdapter } from './adapter';
import type {
  HomeMetric,
  HomeMetricId,
  HomeReadInput,
  HomeReadModel,
  HomeViewConfig,
  HomeViewId,
  HomeWorkflowStage,
  HomeWorkspaceOverview,
} from './types';

const ACTIVE_TASK_STATUSES = new Set([
  'assigned_pending_confirmation',
  'cancel_requested',
  'doing',
  'pending',
  'pending_acceptance',
  'pending_assignment',
  'queued',
  'refund_pending',
  'risk',
  'running',
]);

const HOME_VIEW_CONFIGS: Readonly<Record<HomeViewId, HomeViewConfig>> = {
  'account-manager': {
    cards: [
      {
        id: 'project-health',
        kind: 'project-health',
        title: '项目状态',
        xl: 15,
      },
      { id: 'todos', kind: 'todos', title: '待办事项', xl: 9 },
      { id: 'quick-actions', kind: 'quick-actions', title: '快捷发起', xl: 9 },
      { id: 'tasks', kind: 'tasks', title: '最近任务', xl: 15 },
    ],
    description: '项目日报、项目状态与待办事项。',
    id: 'account-manager',
    label: 'AM 工作台',
    metricIds: [
      'active-projects',
      'active-campaigns',
      'todo-count',
      'risk-items',
    ],
    quickActions: [
      {
        icon: 'lucide:briefcase-business',
        label: '维护项目资料',
        path: '/fusion/projects',
      },
      {
        icon: 'lucide:clipboard-list',
        label: '查看项目待办',
        path: '/workbench/tasks',
      },
    ],
  },
  creative: {
    cards: [
      { id: 'todos', kind: 'todos', title: '待办事项', xl: 9 },
      { id: 'tasks', kind: 'tasks', title: '素材与 AI 任务', xl: 15 },
      { id: 'quick-actions', kind: 'quick-actions', title: '快捷发起', xl: 24 },
    ],
    description: '聚焦素材交付与 AI 制作待办。',
    id: 'creative',
    label: '素材工作台',
    metricIds: ['active-tasks', 'ai-outputs', 'material-ready', 'todo-count'],
    quickActions: [
      {
        icon: 'lucide:file-plus-2',
        label: '新建素材需求',
        path: '/requirement/create',
      },
      {
        icon: 'lucide:library',
        label: '查看素材库',
        path: '/materials/material-library',
      },
    ],
  },
  executive: {
    cards: [
      {
        id: 'project-health',
        kind: 'project-health',
        title: '项目经营',
        xl: 15,
      },
      { id: 'todos', kind: 'todos', title: '经营风险与待办', xl: 9 },
      { id: 'quick-actions', kind: 'quick-actions', title: '快捷入口', xl: 24 },
    ],
    description: '聚焦项目经营、风险与管理决策。',
    id: 'executive',
    label: '管理层工作台',
    metricIds: ['active-projects', 'spend', 'roas', 'risk-items'],
    quickActions: [
      {
        icon: 'lucide:chart-no-axes-combined',
        label: '查看经营报表',
        path: '/data-report',
      },
      {
        icon: 'lucide:briefcase-business',
        label: '查看项目',
        path: '/fusion/projects',
      },
    ],
  },
  media: {
    cards: [
      {
        id: 'account-status',
        kind: 'account-status',
        title: '账号生命周期',
        xl: 15,
      },
      { id: 'todos', kind: 'todos', title: '审批与异常', xl: 9 },
      { id: 'quick-actions', kind: 'quick-actions', title: '快捷发起', xl: 9 },
      { id: 'tasks', kind: 'tasks', title: '最近任务', xl: 15 },
    ],
    description: '查看审批、账号生命周期、限额与异常账号。',
    id: 'media',
    label: '媒介工作台',
    metricIds: [
      'pending-applications',
      'active-assignments',
      'exception-accounts',
      'risk-items',
    ],
    quickActions: [
      {
        icon: 'lucide:clipboard-check',
        label: '处理资源审批',
        path: '/workbench/approvals',
      },
      {
        icon: 'lucide:wallet-cards',
        label: '查看媒体资源',
        path: '/media-resources/accounts',
      },
    ],
  },
  operator: {
    cards: [
      {
        id: 'project-workflow',
        kind: 'project-workflow',
        title: '项目流程摘要',
        xl: 15,
      },
      { id: 'todos', kind: 'todos', title: '待办事项', xl: 9 },
      {
        id: 'account-status',
        kind: 'account-status',
        title: '账号状态',
        xl: 9,
      },
      { id: 'tasks', kind: 'tasks', title: '最近任务', xl: 15 },
      { id: 'quick-actions', kind: 'quick-actions', title: '快捷发起', xl: 24 },
    ],
    description: '负责项目投放数据、待办事项与账号状态。',
    id: 'operator',
    label: '投放工作台',
    metricIds: ['spend', 'roas', 'active-campaigns', 'active-assignments'],
    quickActions: [
      {
        icon: 'lucide:rocket',
        label: '创建多平台广告',
        path: '/fusion/ads/create',
      },
      {
        icon: 'lucide:list-todo',
        label: '查看任务中心',
        path: '/workbench/tasks',
      },
    ],
  },
};

const ROLE_VIEW_ALIASES: Readonly<Record<string, HomeViewId>> = {
  account_manager: 'account-manager',
  'account-manager': 'account-manager',
  admin: 'executive',
  creator: 'creative',
  creative_lead: 'creative',
  'creative-lead': 'creative',
  designer: 'creative',
  executive: 'executive',
  finance: 'executive',
  media: 'media',
  media_lead: 'media',
  'media-lead': 'media',
  operator: 'operator',
  operator_lead: 'operator',
  'operator-lead': 'operator',
};

function countActiveTasks(input: HomeReadInput): number {
  return input.tasks.filter((task) => ACTIVE_TASK_STATUSES.has(task.status))
    .length;
}

function formatMoney(value: number, currency: string): string {
  return new Intl.NumberFormat('zh-CN', {
    currency,
    maximumFractionDigits: 0,
    style: 'currency',
  }).format(value);
}

function metricMap(input: HomeReadInput): Map<HomeMetricId, HomeMetric> {
  const overview = input.overview;
  const activeTasks = countActiveTasks(input);
  const riskItems =
    input.resource.exceptionAccountCount +
    (overview?.todos.filter((todo) => todo.level === 'high').length ?? 0);
  return new Map<HomeMetricId, HomeMetric>([
    [
      'active-assignments',
      {
        description: `${input.resource.pendingReturnCount} 条回收处理中`,
        icon: 'lucide:link-2',
        id: 'active-assignments',
        label: '在用账号',
        value: input.resource.activeAssignmentCount,
      },
    ],
    [
      'active-campaigns',
      {
        description: '来自当前项目工作台概览',
        icon: 'lucide:megaphone',
        id: 'active-campaigns',
        label: '在投广告系列',
        value: overview?.activeCampaigns ?? 0,
      },
    ],
    [
      'active-projects',
      {
        description: '来自项目读模型',
        icon: 'lucide:briefcase-business',
        id: 'active-projects',
        label: '可用项目',
        value: input.projectCount,
      },
    ],
    [
      'active-tasks',
      {
        description: `${input.tasks.length} 个任务已加载`,
        icon: 'lucide:list-todo',
        id: 'active-tasks',
        label: '执行中任务',
        value: activeTasks,
      },
    ],
    [
      'ai-outputs',
      {
        description: '来自当前项目工作台概览',
        icon: 'lucide:sparkles',
        id: 'ai-outputs',
        label: 'AI 产出',
        value: overview?.aiOutputs ?? 0,
      },
    ],
    [
      'exception-accounts',
      {
        description: '异常账号需要媒介处理',
        icon: 'lucide:triangle-alert',
        id: 'exception-accounts',
        label: '异常账号',
        value: input.resource.exceptionAccountCount,
      },
    ],
    [
      'material-ready',
      {
        description: '来自当前项目工作台概览',
        icon: 'lucide:package-check',
        id: 'material-ready',
        label: '可投素材',
        value: overview?.materialReady ?? 0,
      },
    ],
    [
      'pending-applications',
      {
        description: '资源申请等待审批',
        icon: 'lucide:clipboard-check',
        id: 'pending-applications',
        label: '待审批申请',
        value: input.resource.pendingApplicationCount,
      },
    ],
    [
      'risk-items',
      {
        description: '高优先级待办与异常账号合计',
        icon: 'lucide:shield-alert',
        id: 'risk-items',
        label: '风险项',
        value: riskItems,
      },
    ],
    [
      'roas',
      {
        description: '按统一归因口径',
        icon: 'lucide:chart-no-axes-combined',
        id: 'roas',
        label: 'ROAS',
        value: (overview?.roas ?? 0).toFixed(2),
      },
    ],
    [
      'spend',
      {
        description: '当前项目消耗',
        icon: 'lucide:wallet-cards',
        id: 'spend',
        label: '今日消耗',
        value: formatMoney(overview?.spend ?? 0, overview?.currency ?? 'USD'),
      },
    ],
    [
      'todo-count',
      {
        description: '来自当前项目待办',
        icon: 'lucide:clipboard-list',
        id: 'todo-count',
        label: '待办事项',
        value: overview?.todos.length ?? 0,
      },
    ],
  ]);
}

function resolveViewIds(roleCodes: readonly string[]): HomeViewId[] {
  const result: HomeViewId[] = [];
  for (const roleCode of roleCodes) {
    const view = ROLE_VIEW_ALIASES[roleCode.trim().toLowerCase()];
    if (view && !result.includes(view)) result.push(view);
  }
  return result.length > 0 ? result : ['operator'];
}

function workflow(input: HomeReadInput): HomeWorkflowStage[] {
  if (input.workflowStages) {
    return input.workflowStages.map((stage) => ({ ...stage }));
  }
  const overview = input.overview;
  return [
    {
      description: `${countActiveTasks(input)} 个任务排队或执行中`,
      label: '任务与策划',
      value: input.tasks.length,
    },
    {
      description: '图片、视频与 AI 生成结果',
      label: 'AI 制作',
      value: overview?.aiOutputs ?? 0,
    },
    {
      description: '已进入可投放状态的素材',
      label: '审核可投',
      value: overview?.materialReady ?? 0,
    },
    {
      description: '当前项目在投广告系列',
      label: '广告投放',
      value: overview?.activeCampaigns ?? 0,
    },
  ];
}

export class HomeService {
  constructor(private readonly adapter?: HomeOverviewAdapter) {}

  async loadOverview(projectId: string): Promise<HomeWorkspaceOverview> {
    if (!this.adapter) {
      throw new Error('Home overview adapter is not configured');
    }
    return await this.adapter.loadOverview(projectId);
  }

  read(input: HomeReadInput): HomeReadModel {
    const availableViews = resolveViewIds(input.roleCodes).map(
      (viewId) => HOME_VIEW_CONFIGS[viewId],
    );
    const metrics = metricMap(input);
    const defaultView = availableViews[0] ?? HOME_VIEW_CONFIGS.operator;
    const riskItems = metrics.get('risk-items')?.value ?? 0;
    return {
      accountStatus: [
        {
          description: '已完成申请分配并处于使用中',
          label: '在用账号',
          value: input.resource.activeAssignmentCount,
        },
        {
          description: '等待审批或补充资料的资源申请',
          label: '待审批',
          value: input.resource.pendingApplicationCount,
        },
        {
          description: '风控、限额或其他异常状态',
          label: '异常账号',
          value: input.resource.exceptionAccountCount,
        },
        {
          description: '请求归还但尚未完成的账号',
          label: '回收处理中',
          value: input.resource.pendingReturnCount,
        },
      ],
      availableViews,
      defaultViewId: defaultView.id,
      metrics: [...metrics.values()],
      projectHealth: [
        {
          description: '来自项目读模型',
          label: '可用项目',
          value: input.projectCount,
        },
        {
          description: '当前项目在投广告系列',
          label: '在投系列',
          value: input.overview?.activeCampaigns ?? 0,
        },
        {
          description: '按统一归因口径',
          label: 'ROAS',
          value: Number((input.overview?.roas ?? 0).toFixed(2)),
        },
        {
          description: '高优先级待办与异常账号',
          label: '风险项',
          value: typeof riskItems === 'number' ? riskItems : 0,
        },
      ],
      tasks: input.tasks.slice(0, 4).map((task) => ({ ...task })),
      todos: input.overview?.todos.map((todo) => ({ ...todo })) ?? [],
      workflow: workflow(input),
    };
  }

  resolveView(
    model: HomeReadModel,
    requestedViewId: HomeViewId | undefined,
  ): HomeViewConfig {
    return (
      model.availableViews.find((view) => view.id === requestedViewId) ??
      model.availableViews.find((view) => view.id === model.defaultViewId) ??
      HOME_VIEW_CONFIGS.operator
    );
  }
}
