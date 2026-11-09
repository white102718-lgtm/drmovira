export type HomeCardKind =
  | 'account-status'
  | 'project-health'
  | 'project-workflow'
  | 'quick-actions'
  | 'tasks'
  | 'todos';

export type HomeMetricId =
  | 'active-assignments'
  | 'active-campaigns'
  | 'active-projects'
  | 'active-tasks'
  | 'ai-outputs'
  | 'exception-accounts'
  | 'material-ready'
  | 'pending-applications'
  | 'risk-items'
  | 'roas'
  | 'spend'
  | 'todo-count';

export type HomeTodoLevel = 'high' | 'low' | 'medium';

export type HomeViewId =
  | 'account-manager'
  | 'creative'
  | 'executive'
  | 'media'
  | 'operator';

export interface HomeCardConfig {
  id: string;
  kind: HomeCardKind;
  title: string;
  xl: number;
}

export interface HomeMetric {
  description: string;
  icon: string;
  id: HomeMetricId;
  label: string;
  value: number | string;
}

export interface HomeQuickAction {
  icon: string;
  label: string;
  path: string;
}

export interface HomeResourceSnapshot {
  activeAssignmentCount: number;
  exceptionAccountCount: number;
  pendingApplicationCount: number;
  pendingReturnCount: number;
}

export interface HomeTaskReadModel {
  id: string;
  platform?: string;
  progress: number;
  projectId: string;
  status: string;
  targetPath?: string;
  title: string;
  updatedAt: string;
}

export interface HomeTodo {
  description: string;
  id: string;
  level: HomeTodoLevel;
  targetPath: string;
  title: string;
}

export interface HomeViewConfig {
  cards: readonly HomeCardConfig[];
  description: string;
  id: HomeViewId;
  label: string;
  metricIds: readonly HomeMetricId[];
  quickActions: readonly HomeQuickAction[];
}

export interface HomeWorkspaceOverview {
  activeCampaigns: number;
  activeTasks: number;
  aiOutputs: number;
  conversions: number;
  currency: string;
  materialReady: number;
  projectId: string;
  roas: number;
  spend: number;
  todos: readonly HomeTodo[];
}

export interface HomeWorkflowStage {
  description: string;
  label: string;
  value: number;
}

export interface HomeReadInput {
  overview: HomeWorkspaceOverview | null;
  projectCount: number;
  resource: HomeResourceSnapshot;
  roleCodes: readonly string[];
  tasks: readonly HomeTaskReadModel[];
  /** Activity-derived stages replace the former template-only workflow count. */
  workflowStages?: readonly HomeWorkflowStage[];
}

export interface HomeReadModel {
  accountStatus: readonly HomeWorkflowStage[];
  availableViews: readonly HomeViewConfig[];
  defaultViewId: HomeViewId;
  metrics: readonly HomeMetric[];
  projectHealth: readonly HomeWorkflowStage[];
  tasks: readonly HomeTaskReadModel[];
  todos: readonly HomeTodo[];
  workflow: readonly HomeWorkflowStage[];
}
