import { HttpAdDashboardAdapter } from './adapters/http';
import { MockAdDashboardAdapter } from './adapters/mock';
import { AdDashboardService } from './service';

export type { AdDashboardAdapter } from './adapter';
export { HttpAdDashboardAdapter } from './adapters/http';
export { MockAdDashboardAdapter } from './adapters/mock';
export { formatAdDashboardValue } from './format';
export {
  adDashboardCategoryOrder,
  adDashboardSchemas,
  getAdDashboardSchema,
  resolveAdDashboardCategory,
} from './schema';
export { AdDashboardService } from './service';
export { getAdDashboardStatusOptions } from './status';
export type * from './types';

const useMockAdapter = import.meta.env.VITE_FUSION_DEMO_MODE === 'true';

export const adDashboardService = new AdDashboardService(
  useMockAdapter ? new MockAdDashboardAdapter() : new HttpAdDashboardAdapter(),
);
