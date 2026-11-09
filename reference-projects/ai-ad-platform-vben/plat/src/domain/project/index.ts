import { HttpProjectAdapter } from './adapters/http';
import { MockProjectAdapter } from './adapters/mock';
import { ProjectService } from './service';

export type { ProjectAdapter } from './adapter';
export { HttpProjectAdapter } from './adapters/http';
export { MockProjectAdapter } from './adapters/mock';
export { PROJECT_CLOSURE_APPLICATION_CODE } from './project-closure';
export {
  listProjectAgencyLineSyncBatches,
  listProjectAgencyLineSyncFailures,
  synchronizeProjectAgencyLines,
} from './agency-line-sync';
export { ProjectService } from './service';
export type * from './types';

const useMockAdapter = import.meta.env.VITE_FUSION_DEMO_MODE === 'true';

export const projectService = new ProjectService(
  useMockAdapter ? new MockProjectAdapter() : new HttpProjectAdapter(),
);
