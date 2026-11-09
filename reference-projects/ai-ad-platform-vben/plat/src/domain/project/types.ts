/** 项目管理页签总数，不受列表筛选或分页影响。 */
export interface ProjectTabCounts {
  agencyLineCount: number;
  projectCount: number;
}

/** 项目下拉的轻量选项，不携带项目详情和关联集合。 */
export interface ProjectSearchOption {
  id: string;
  name: string;
}

/** 项目关联代理线的轻量投放链接选项。 */
export interface ProjectAgencyLineDeliveryOption {
  deliveryUrl: string;
  id: string;
  name: string;
  platform: string;
}

export type {
  ProjectAgencyLineOption,
  ProjectContext,
  ProjectContextOption,
  ProjectListParams,
  ProjectListResult,
  ProjectOperatingOverview,
  ProjectOption,
  ProjectRegionOption,
  ProjectSummary,
  ProjectUpsertPayload,
  ProjectWallet,
} from '#/api/fusion/types';

export interface ProjectAgencyLineBindingInput {
  add?: string[];
  remove?: string[];
  requestId?: string;
}
