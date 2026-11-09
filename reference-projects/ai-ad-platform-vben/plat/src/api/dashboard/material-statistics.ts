import { adpulseClient, otherClient } from '#/api/request';
import { pollUploadTask } from '#/api/utils/poll-task';

export function getMaterialStatistics(
  start_date: null | string = null,
  end_date: null | string = null,
  game_platform: null | string = null,
  ad_platform: null | string = null,
  agent_line: null | string = null,
  ad_name: null | string = null,
  page: number = 1,
  page_size: number = 50,
): Promise<any> {
  return otherClient.get('/api/data/range', {
    params: {
      end_date,
      start_date,
      ...(game_platform === null ? {} : { game_platform }),
      ...(ad_platform === null ? {} : { ad_platform }),
      ...(agent_line === null ? {} : { agent_line }),
      ...(ad_name === null ? {} : { ad_name }),
      page,
      page_size,
    },
  });
}
export function getMaterialRecommend(
  params: Record<string, any> = {},
): Promise<any> {
  return otherClient.get('/api/materials/recommend', {
    params: Object.fromEntries(
      Object.entries(params).filter(([_, value]) => value !== null),
    ),
  });
}

// ==================== 素材数据看板 ====================

export interface MaterialDesignerItem {
  amount?: number;
  date?: string;
  name: string;
  spend?: number;
  department: string;
  tokens?: number;
}

export interface MaterialDashboardSummary {
  avg_ctr: number;
  avg_ir: number;
  avg_svr: number;
  ctr_trend: number;
  ir_trend: number;
  spend_trend: number;
  svr_trend: number;
  total_count: number;
  total_spend: number;
  update_date: string;
}

export interface MaterialPersonnelConsumptionResponse {
  list: MaterialDesignerItem[];
  spend_total: number;
  tokens_total?: number;
  total: number;
}

export function getMaterialDashboard(params: {
  department?: string;
  end_date?: string;
  group_by?: 'person_day';
  include_tokens?: boolean;
  keyword?: string;
  order?: 'asc' | 'desc';
  page?: number;
  page_size?: number;
  start_date?: string;
}): Promise<MaterialPersonnelConsumptionResponse> {
  return adpulseClient.get('/material-dashboard/designer-spend', { params });
}

function buildMaterialBoardUrlParams(params: Record<string, any>): URLSearchParams {
  const urlParams = new URLSearchParams();
  const arrayKeys = new Set(['creators', 'designers', 'basenames']);

  Object.entries(params).forEach(([key, value]) => {
    if (arrayKeys.has(key)) return;
    if (value !== undefined && value !== null && value !== '') {
      urlParams.set(key, String(value));
    }
  });

  for (const key of ['creators', 'designers']) {
    const val = params[key];
    if (Array.isArray(val) && val.length > 0) {
      val.forEach((v: string) => urlParams.append(key, v));
    }
  }

  if (params.basenames) {
    String(params.basenames).split(',').map((s) => s.trim()).filter(Boolean)
      .forEach((v) => urlParams.append('basenames', v));
  }

  return urlParams;
}

export function getMaterialBoardList(params: Record<string, any>): Promise<any> {
  return adpulseClient.get(`material-dashboard/materials?${buildMaterialBoardUrlParams(params).toString()}`);
}

export async function exportMaterialBoard(params: Record<string, any>): Promise<{ content: string; filename: string }> {
  const res: any = await adpulseClient.get(`material-dashboard/materials/export?${buildMaterialBoardUrlParams(params).toString()}`);
  return pollUploadTask(res.task_id, 0, undefined, 6000, true);
}

export function getMaterialAds(params: Record<string, any>): Promise<any> {
  return adpulseClient.get('/material-dashboard/materials/ads', { params });
}
