import { adpulseClient } from '#/api/request';

export type CompareMode = 'mom' | 'yoy';
export type CompareLevel = 'ad' | 'adset' | 'agent_line' | 'campaign';

export interface PerformanceComparisonQuery {
  account_id?: string;
  agent_line?: string;
  base_time: string;
  compare_offsets?: number[];
  compare_times?: string[];
  force_refresh?: boolean;
  game_platform?: string;
  level: CompareLevel;
  limit?: number;
  media_buyer?: string;
  metrics?: string[];
  mode: CompareMode;
  object_id?: string;
  project_id?: string;
}

export interface MetricPoint {
  metrics: Record<string, number>;
  role: string;
  time: string;
}

export interface ComparisonMetric {
  base: number;
  compare: number;
  delta: number;
  delta_rate: null | number;
}

export interface MetricComparison {
  metrics: Record<string, ComparisonMetric>;
  time: string;
}

export interface PerformanceItem {
  comparisons: MetricComparison[];
  level: string;
  object_id: string;
  object_name: string;
  points: MetricPoint[];
}

export interface PerformanceComparisonResult {
  cache: { cache_key: string; hit: boolean };
  items: PerformanceItem[];
  metrics: string[];
  request: Record<string, any>;
  time_points: string[];
  total: number;
}

interface ApiResponse<T> {
  code: number;
  data: T;
  message: string;
}

export async function queryPerformanceComparison(
  data: PerformanceComparisonQuery,
): Promise<PerformanceComparisonResult> {
  const res = await adpulseClient.post<ApiResponse<PerformanceComparisonResult>>(
    '/performance-comparison/query',
    data,
    { responseReturn: 'body' },
  );
  return (res as any).data;
}
