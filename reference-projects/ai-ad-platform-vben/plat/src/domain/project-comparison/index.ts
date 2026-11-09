import { projectService } from '#/domain/project';

import { MockProjectComparisonAdapter } from './adapters/mock';
import { ProjectComparisonService } from './service';

export type { ProjectComparisonAdapter } from './adapter';
export type { ProjectComparisonFormalTransport } from './adapter';
export { HttpProjectComparisonAdapter } from './adapters/formal-http';
export { MockProjectComparisonAdapter } from './adapters/mock';
export {
  projectComparisonMetricConfigByKey,
  projectComparisonMetricConfigs,
} from './metric-config';
export { PROJECT_COMPARISON_DEMO_AS_OF } from './mock-data';
export { buildProjectComparisonReviewDraft } from './report';
export type { ProjectComparisonReviewDraft } from './report';
export { ProjectComparisonService } from './service';
export type * from './types';

/**
 * The P0 product deliberately exposes only the deterministic Mock adapter.
 * The formal HTTP adapter is deferred until backend supplies project/line
 * authorization, consistent metric cut-off and financial ledger contracts.
 */
export const projectComparisonService = new ProjectComparisonService(
  new MockProjectComparisonAdapter(),
  projectService,
);
