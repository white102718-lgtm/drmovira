import type { HomeWorkspaceOverview } from './types';

/** Read-only dashboard boundary; no card renderer writes business state. */
export interface HomeOverviewAdapter {
  loadOverview(projectId: string): Promise<HomeWorkspaceOverview>;
}
