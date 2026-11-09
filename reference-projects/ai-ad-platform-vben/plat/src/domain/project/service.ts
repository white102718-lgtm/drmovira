import type { ProjectAdapter } from './adapter';
import { validateProductInfo } from './validation';
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

export class ProjectService {
  constructor(private readonly adapter: ProjectAdapter) {}

  applyAgencyLineBindings(
    id: string,
    input: ProjectAgencyLineBindingInput,
  ): Promise<ProjectSummary> {
    if (!id.trim()) return Promise.reject(new Error('项目 ID 不能为空'));
    const add = [...new Set(input.add ?? [])];
    const remove = [...new Set(input.remove ?? [])];
    if ([...add, ...remove].some((lineId) => !lineId.trim())) {
      return Promise.reject(new Error('代理线 ID 不能为空'));
    }
    if (add.some((lineId) => remove.includes(lineId))) {
      return Promise.reject(new Error('同一代理线不能同时绑定和解绑'));
    }
    return this.adapter.applyAgencyLineBindings(id, {
      add,
      remove,
      requestId: input.requestId,
    });
  }

  bindAgencyLines(
    id: string,
    agencyLineIds: string[],
  ): Promise<ProjectSummary> {
    if (!id.trim()) return Promise.reject(new Error('项目 ID 不能为空'));
    if (agencyLineIds.some((lineId) => !lineId.trim())) {
      return Promise.reject(new Error('代理线 ID 不能为空'));
    }
    return this.adapter.bindAgencyLines(id, [...new Set(agencyLineIds)]);
  }

  createWallet(id: string): Promise<ProjectWallet> {
    if (!id.trim()) return Promise.reject(new Error('项目 ID 不能为空'));
    return this.adapter.createWallet(id);
  }

  get(id: string): Promise<ProjectSummary> {
    return this.adapter.get(id);
  }

  getContext(): Promise<ProjectContext> {
    return this.adapter.getContext();
  }

  /** 查询独立页签总数，避免依赖尚未加载的列表。 */
  getTabCounts(): Promise<ProjectTabCounts> {
    return this.adapter.getTabCounts();
  }

  getOperatingOverview(id: string): Promise<ProjectOperatingOverview> {
    return this.adapter.getOperatingOverview(id);
  }

  list(query: ProjectListParams = {}): Promise<ProjectListResult> {
    return this.adapter.list(query);
  }

  listAgencyLines(): Promise<ProjectAgencyLineOption[]> {
    return this.adapter.listAgencyLines();
  }

  /** 查询项目关联代理线的轻量投放链接选项。 */
  listAgencyLineDeliveryOptions(
    projectId: string,
  ): Promise<ProjectAgencyLineDeliveryOption[]> {
    if (!projectId.trim()) return Promise.reject(new Error('项目 ID 不能为空'));
    return this.adapter.listAgencyLineDeliveryOptions(projectId);
  }

  listOptions(): Promise<ProjectOption[]> {
    return this.adapter.listOptions();
  }

  listRegionOptions(): Promise<ProjectRegionOption[]> {
    return this.adapter.listRegionOptions();
  }

  /** 查询当前用户项目数据范围内的轻量下拉选项。 */
  searchScopedOptions(keyword?: string): Promise<ProjectSearchOption[]> {
    return this.adapter.searchScopedOptions(keyword?.trim() || undefined);
  }

  /** 查询全部项目的轻量下拉选项，不应用项目列表数据范围。 */
  searchOptions(keyword?: string): Promise<ProjectSearchOption[]> {
    return this.adapter.searchOptions(keyword?.trim() || undefined);
  }

  save(input: ProjectUpsertPayload): Promise<ProjectSummary> {
    if (input.serviceFeePercent < 0 || input.serviceFeePercent > 100) {
      return Promise.reject(new Error('服务费必须在 0–100 之间'));
    }
    if (input.agencyLineIds?.some((id) => !id.trim())) {
      return Promise.reject(new Error('代理线 ID 不能为空'));
    }
    try {
      validateProductInfo(input.productInfo);
      this.validateStableUserPair(input.amUserId, input.amName, 'AM', true);
      this.validateStableUserPair(
        input.deliveryLeaderId,
        input.deliveryLeaderName,
        '投放负责人',
      );
    } catch (error) {
      return Promise.reject(error);
    }
    return this.adapter.save(input);
  }

  private validateStableUserPair(
    id: string | undefined,
    name: string | undefined,
    label: string,
    allowLegacyName = false,
  ) {
    const hasId = Boolean(id?.trim());
    const hasName = Boolean(name?.trim());
    if ((hasId && !hasName) || (!allowLegacyName && !hasId && hasName)) {
      throw new Error(`${label}必须同时保存稳定用户 ID 和姓名`);
    }
  }
}
