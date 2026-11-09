import type {
  ProjectAgencyLineBindingInput,
  ProjectAgencyLineDeliveryOption,
  ProjectAgencyLineOption,
  ProjectContext,
  ProjectTabCounts,
  ProjectListParams,
  ProjectListResult,
  ProjectOperatingOverview,
  ProjectOption,
  ProjectRegionOption,
  ProjectSearchOption,
  ProjectSummary,
  ProjectUpsertPayload,
  ProjectWallet,
} from './types';

export interface ProjectAdapter {
  applyAgencyLineBindings(
    id: string,
    input: ProjectAgencyLineBindingInput,
  ): Promise<ProjectSummary>;
  bindAgencyLines(id: string, agencyLineIds: string[]): Promise<ProjectSummary>;
  createWallet(id: string): Promise<ProjectWallet>;
  getContext(): Promise<ProjectContext>;
  getTabCounts(): Promise<ProjectTabCounts>;
  get(id: string): Promise<ProjectSummary>;
  getOperatingOverview(id: string): Promise<ProjectOperatingOverview>;
  list(query?: ProjectListParams): Promise<ProjectListResult>;
  listAgencyLines(): Promise<ProjectAgencyLineOption[]>;
  listAgencyLineDeliveryOptions(
    projectId: string,
  ): Promise<ProjectAgencyLineDeliveryOption[]>;
  listOptions(): Promise<ProjectOption[]>;
  listRegionOptions(): Promise<ProjectRegionOption[]>;
  /** 查询当前用户项目数据范围内的轻量下拉选项。 */
  searchScopedOptions(keyword?: string): Promise<ProjectSearchOption[]>;
  /** 查询全部项目的轻量下拉选项，不应用项目列表数据范围。 */
  searchOptions(keyword?: string): Promise<ProjectSearchOption[]>;
  save(input: ProjectUpsertPayload): Promise<ProjectSummary>;
}
