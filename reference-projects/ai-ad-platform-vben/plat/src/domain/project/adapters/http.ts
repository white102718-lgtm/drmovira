import type { ProjectAdapter } from '../adapter';
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
} from '../types';

import { mainBackendClient } from '#/api/request';
import { FULL_OPTION_PAGE_SIZE } from '#/constants/pagination';
import { agencyLineService } from '#/domain/agency-line';

export class HttpProjectAdapter implements ProjectAdapter {
  createWallet(id: string): Promise<ProjectWallet> {
    return mainBackendClient.post(
      `/project/projects/${encodeURIComponent(id)}/wallet`,
    );
  }

  applyAgencyLineBindings(
    id: string,
    input: ProjectAgencyLineBindingInput,
  ): Promise<ProjectSummary> {
    return mainBackendClient.request(
      `/project/projects/${encodeURIComponent(id)}/agency-line-bindings`,
      { data: input, method: 'PATCH' },
    );
  }

  bindAgencyLines(
    id: string,
    agencyLineIds: string[],
  ): Promise<ProjectSummary> {
    return mainBackendClient.put(
      `/project/projects/${encodeURIComponent(id)}/agency-lines`,
      { agencyLineIds },
    );
  }

  get(id: string): Promise<ProjectSummary> {
    return mainBackendClient.get(`/project/projects/${encodeURIComponent(id)}`);
  }

  getContext(): Promise<ProjectContext> {
    return mainBackendClient.get('/project/projects/context');
  }

  getTabCounts(): Promise<ProjectTabCounts> {
    return mainBackendClient.get('/project/projects/tab-counts');
  }

  getOperatingOverview(id: string): Promise<ProjectOperatingOverview> {
    return mainBackendClient.get(
      `/project/projects/${encodeURIComponent(id)}/operating-overview`,
    );
  }

  list(query: ProjectListParams = {}): Promise<ProjectListResult> {
    return mainBackendClient.get('/project/projects', { params: query });
  }

  async listAgencyLines(): Promise<ProjectAgencyLineOption[]> {
    const lines = await agencyLineService.listOptions({});
    return lines
      .filter((line) =>
        ['facebook', 'google', 'tiktok', 'kwai'].includes(line.platform),
      )
      .map((line) => ({
        id: line.id,
        name: line.name,
        platform: line.platform as ProjectAgencyLineOption['platform'],
      }));
  }

  listAgencyLineDeliveryOptions(
    projectId: string,
  ): Promise<ProjectAgencyLineDeliveryOption[]> {
    return mainBackendClient.get(
      `/project/projects/${encodeURIComponent(projectId)}/agency-line-options`,
    );
  }

  async listOptions(): Promise<ProjectOption[]> {
    const result = await this.list({
      page: 1,
      pageSize: FULL_OPTION_PAGE_SIZE,
    });
    return result.items.map(
      ({ deliveryLines, id, name, productName, status }) => ({
        deliveryLines,
        id,
        name,
        productName,
        status,
      }),
    );
  }

  listRegionOptions(): Promise<ProjectRegionOption[]> {
    return mainBackendClient.get('/project/projects/region-options');
  }

  /** 查询当前用户项目数据范围内的轻量下拉选项。 */
  searchScopedOptions(keyword?: string): Promise<ProjectSearchOption[]> {
    return mainBackendClient.get('/project/projects/options/scoped', {
      params: { keyword },
    });
  }

  /** 查询全部项目的轻量下拉选项，不应用项目列表数据范围。 */
  searchOptions(keyword?: string): Promise<ProjectSearchOption[]> {
    return mainBackendClient.get('/project/projects/options', {
      params: { keyword },
    });
  }

  save(input: ProjectUpsertPayload): Promise<ProjectSummary> {
    return input.id
      ? mainBackendClient.put(`/project/projects/${input.id}`, input)
      : mainBackendClient.post('/project/projects', input);
  }
}
