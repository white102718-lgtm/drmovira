import type {
  ProjectComparisonQuery,
  ProjectComparisonSourceData,
} from './types';

export interface ProjectComparisonAdapter {
  getSourceData(
    query: ProjectComparisonQuery,
  ): Promise<ProjectComparisonSourceData>;
}

/**
 * Transport is injected only after the backend has documented its endpoint,
 * authentication and service-side authorization scope. No browser-side user
 * identity is accepted here, and no legacy dashboard request is reused.
 */
export interface ProjectComparisonFormalTransport {
  getOverviewSource(input: ProjectComparisonQuery): Promise<unknown>;
}
