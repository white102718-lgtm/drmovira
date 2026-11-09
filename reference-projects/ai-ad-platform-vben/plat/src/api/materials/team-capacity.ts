import { adpulseClient } from '#/api/request';

/** 新单按最后送审、旧单按整单交付日期筛选；日期均为北京时间。 */
export interface TeamCapacityParams {
  end_date: string;
  page?: number;
  page_size?: 50 | 100 | 200;
  sort_by?: 'delivered' | 'hours' | 'rework_count';
  person_id?: string;
  project_id?: string;
  start_date: string;
  task_type?: 'image' | 'video';
}

/** 件数、工单数与人员工单耗时各自独立，缺少历史的比例和耗时返回 null。 */
export interface CapacityMetrics {
  approved: number;
  avg_hours: null | number;
  deadline_order_count: number;
  delivered: number;
  first_pass_orders: number;
  first_pass_rate: null | number;
  hours: null | number;
  image_count: number;
  on_time_orders: number;
  on_time_rate: null | number;
  order_count: number;
  quality_order_count: number;
  reviewed_order_count: number;
  rework_count: null | number;
  rework_orders: null | number;
  rework_rate: null | number;
  timed_delivered: number;
  timed_order_count: number;
  video_count: number;
}

export interface CapacityRow extends CapacityMetrics {
  person: string;
  person_id: string;
  project: string;
  project_id: string;
  task_types: string[];
}

export interface TeamCapacityReport {
  items: CapacityRow[];
  page: number;
  page_size: 50 | 100 | 200;
  /** 当前筛选的项目／人员总行数；summary 始终覆盖全部行。 */
  total: number;
  summary: CapacityMetrics & {
    person_count: number;
    unique_order_count: number;
  };
}

export function getTeamCapacity(
  params: TeamCapacityParams,
  signal?: AbortSignal,
) {
  return adpulseClient.get<TeamCapacityReport>(
    'material-dashboard/team-capacity',
    {
      params,
      signal,
      skipErrorMessage: true,
    },
  );
}

/** 导出沿用同一筛选与排序，按接口允许的最大页逐页读取，避免只导出当前页。 */
export async function getAllTeamCapacityRows(
  params: Omit<TeamCapacityParams, 'page' | 'page_size'>,
  signal?: AbortSignal,
) {
  const rows: CapacityRow[] = [];
  const pageSize = 200;
  let expectedTotal: number | undefined;
  for (let page = 1; ; page += 1) {
    const result = await getTeamCapacity(
      { ...params, page, page_size: pageSize },
      signal,
    );
    if (!Number.isInteger(result.total) || result.total < 0)
      throw new Error('Invalid capacity total');
    expectedTotal ??= result.total;
    // 汇总行在导出期间变化时提示重试，避免下载缺行或重复的报表。
    if (result.total !== expectedTotal)
      throw new Error('Capacity rows changed');
    rows.push(...result.items);
    if (rows.length >= result.total) break;
    if (result.items.length === 0) throw new Error('Incomplete capacity page');
  }
  const keys = new Set(
    rows.map((row) => JSON.stringify([row.project_id, row.person_id])),
  );
  if (keys.size !== rows.length || rows.length !== expectedTotal) {
    throw new Error('Inconsistent capacity pages');
  }
  return rows;
}
