import { HttpPersonnelDashboardAdapter } from './adapters/http';
import { MockPersonnelDashboardAdapter } from './adapters/mock';
import { PersonnelDashboardService } from './service';

export type { PersonnelDashboardAdapter } from './adapter';
export { HttpPersonnelDashboardAdapter } from './adapters/http';
export { MockPersonnelDashboardAdapter } from './adapters/mock';
export { formatPersonnelDashboardValue } from './format';
export {
  getPersonnelDashboardSchema,
  personnelDashboardCategoryOrder,
  personnelDashboardSchemas,
  resolvePersonnelDashboardCategory,
} from './schema';
export { PersonnelDashboardService } from './service';
export type * from './types';

const useMockAdapter = import.meta.env.VITE_FUSION_DEMO_MODE === 'true';

export const personnelDashboardService = new PersonnelDashboardService(
  useMockAdapter
    ? new MockPersonnelDashboardAdapter()
    : new HttpPersonnelDashboardAdapter(),
);
