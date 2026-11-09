import type { HomeOverviewAdapter } from '../adapter';
import type { HomeWorkspaceOverview } from '../types';

import { getWorkspaceOverviewApi } from '#/api';

function requiredProjectId(projectId: string): string {
  const normalized = projectId.trim();
  if (!normalized) throw new Error('工作台概览缺少稳定项目 ID');
  return normalized;
}

/** Compatibility wrapper for the established workspace overview endpoint. */
export class HttpHomeOverviewAdapter implements HomeOverviewAdapter {
  async loadOverview(projectId: string): Promise<HomeWorkspaceOverview> {
    const overview = await getWorkspaceOverviewApi(
      requiredProjectId(projectId),
    );
    return {
      activeCampaigns: overview.activeCampaigns,
      activeTasks: overview.activeTasks,
      aiOutputs: overview.aiOutputs,
      conversions: overview.conversions,
      currency: overview.currency,
      materialReady: overview.materialReady,
      projectId: overview.projectId,
      roas: overview.roas,
      spend: overview.spend,
      todos: overview.todos.map((todo) => ({ ...todo })),
    };
  }
}
