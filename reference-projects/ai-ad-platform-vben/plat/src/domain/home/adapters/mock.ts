import type { HomeOverviewAdapter } from '../adapter';
import type { HomeWorkspaceOverview } from '../types';

/** Injectable Mock boundary for deterministic role-home tests and previews. */
export class MockHomeOverviewAdapter implements HomeOverviewAdapter {
  constructor(
    private readonly load: (
      projectId: string,
    ) => HomeWorkspaceOverview | Promise<HomeWorkspaceOverview>,
  ) {}

  async loadOverview(projectId: string): Promise<HomeWorkspaceOverview> {
    return structuredClone(await this.load(projectId));
  }
}
