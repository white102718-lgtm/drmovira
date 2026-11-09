import { mainBackendClient } from './request';

/** 素材师月报按任务线查询花费的精确筛选条件。 */
export interface MaterialSettlementTaskLineSpendQueryItem {
  projectName: string;
  taskLineName: string;
}

/** 素材师月报任务线花费查询结果。amount 为 null 表示没有匹配到广告数据。 */
export interface MaterialSettlementTaskLineSpend {
  amount: null | number;
  currency: string;
  projectName: string;
  taskLineName: string;
}

interface MaterialSettlementTaskLineSpendResponse {
  items: MaterialSettlementTaskLineSpend[];
}

/**
 * 将一个月报中的全部任务线交由主业务服务批量查询。
 *
 * 服务端按“项目 + 代理线”精确过滤 Doris 明细，避免详情弹窗按任务线逐条请求广告看板接口。
 */
export function queryMaterialSettlementTaskLineSpendsApi(
  settlementMonth: string,
  taskLines: MaterialSettlementTaskLineSpendQueryItem[],
) {
  return mainBackendClient
    .post<MaterialSettlementTaskLineSpendResponse>(
      '/material-settlement/task-line-spends',
      {
        settlementMonth,
        taskLines,
      },
    )
    .then((response) => response.items);
}
