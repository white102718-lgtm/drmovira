import { mainBackendClient } from './request';

/** 新建项目绑定代理线所需的最小展示字段。 */
export interface UnboundAgencyLineOption {
  id: string;
  name: string;
}

/** 按名称搜索未绑定项目的代理线，最多返回五十条。 */
export function getUnboundAgencyLineOptions(keyword: string) {
  return mainBackendClient.get<UnboundAgencyLineOption[]>(
    '/project/agency-lines/unbound-options',
    { params: { keyword } },
  );
}
