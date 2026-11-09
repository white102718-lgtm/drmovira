import type { AdDashboardListQuery, AdDashboardListResult } from './types';

export interface AdDashboardAdapter {
  list(query: AdDashboardListQuery): Promise<AdDashboardListResult>;
}
