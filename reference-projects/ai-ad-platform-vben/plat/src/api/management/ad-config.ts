import { adpulseClient } from '#/api/request';

export type AdConfigPullType = 'activities' | 'config';
export type AdConfigLevel = 'ad' | 'adset' | 'campaign';
export type AdConfigStatus = 'done' | 'failed' | 'pending';

/**
 * 一个系列/组/广告一条,归属靠 campaign_id + ad_set_id;列表接口不返回 config/activities 大字段。
 * 提交时即插入 pending 种子文档,worker 拉完更新为 done/failed;树内其他对象为 done。
 */
export interface AdConfigObject {
  _id: string;
  account_id: string;
  account_name: string;
  activities?: any[];
  ad_set_id: null | string;
  campaign_id: null | string;
  config?: any;
  created_at: string;
  date?: null | string;
  error?: null | string;
  include_related?: boolean;
  level: AdConfigLevel;
  object_id: string;
  pull_type: AdConfigPullType;
  real_name: string;
  request_id: string;
  status: AdConfigStatus;
}

export interface AdConfigRecordListParams {
  level?: AdConfigLevel;
  object_id?: string;
  page?: number;
  page_size?: number;
  pull_type: AdConfigPullType;
}

/** 提交拉取配置任务(广告/组/系列,include_related 拉整棵系列树) */
export function submitAdConfigPull(data: {
  ids: string[];
  include_related: boolean;
  level: AdConfigLevel;
}) {
  return adpulseClient.post<{ request_ids: string[] }>('/ad-config/config', data);
}

/** 提交拉取某天 FB 操作记录任务(广告/组/系列,include_related 拉整棵系列树) */
export function submitAdActivitiesPull(data: {
  date: string;
  ids: string[];
  include_related: boolean;
  level: AdConfigLevel;
}) {
  return adpulseClient.post<{ request_ids: string[] }>(
    '/ad-config/operations',
    data,
  );
}

/** 查看对象配置:已拉取过直接返回 done+object,否则提交拉取返回 pending;include_children 附带下级组/广告配置 */
export function viewAdConfig(data: {
  include_children?: boolean;
  level: AdConfigLevel;
  object_id: string;
}) {
  return adpulseClient.post<{
    children?: AdConfigObject[];
    object?: AdConfigObject;
    request_id?: string;
    status: 'done' | 'pending';
  }>('/ad-config/config-view', data);
}

/** 一条 FB 操作记录 + 该操作时点的成效快照(快照字段见 snapshot_columns) */
export interface AdOperationRecord {
  actor_id?: string;
  actor_name?: string;
  /** 变更展示:预算改成人类可读,其余原样 */
  change?: string;
  /** 变更前(预算金额 / 开启关闭状态等) */
  change_before?: string;
  /** 变更后 */
  change_after?: string;
  /** 账户当地时区的时间串(FB 原始) */
  date_time_in_timezone?: string;
  event_time?: number | string;
  /** 操作时刻转成的中国时间(和快照匹配同一套),时间列显示这个 */
  event_time_china?: null | string;
  event_type?: string;
  extra_data?: string;
  object_id?: string;
  object_name?: string;
  snapshot: null | Record<string, any>;
  translated_event_type?: string;
}

/**
 * 查看对象某天操作记录:已拉取直接返回 done+records,否则提交拉取返回 pending。force=强制重拉。
 * find_latest=从 date 逐天回溯到该对象最近一次有操作的天(上限30天),
 * 回溯中遇到未缓存的天返回 pending+probe_date,前端轮询推进。
 */
export function viewAdOperations(data: {
  date: string;
  find_latest?: boolean;
  force?: boolean;
  level: AdConfigLevel;
  object_id: string;
}) {
  return adpulseClient.post<{
    /** find_latest 命中的天;null=回溯范围内无操作 */
    found_date?: null | string;
    /** pending 时正在拉取的天 */
    probe_date?: string;
    records?: AdOperationRecord[];
    request_id?: string;
    /** find_latest 未命中时已回溯的天数 */
    searched_days?: number;
    snapshot_columns?: string[];
    status: 'done' | 'pending';
    /** 上次真实拉取完成时间(中国时间字符串) */
    updated_at?: null | string;
  }>('/ad-config/operations-view', data);
}

/** 已拉取对象列表 */
export function getAdConfigRecords(params: AdConfigRecordListParams) {
  return adpulseClient.get<{
    items: AdConfigObject[];
    page: number;
    page_size: number;
    total: number;
  }>('/ad-config/records', { params });
}

/** 按提交批次查完整结果(同一次拉取的所有对象,含 config/activities) */
export function getAdConfigResult(requestId: string, pullType: AdConfigPullType) {
  return adpulseClient.get<{ objects: AdConfigObject[] }>(
    `/ad-config/result/${requestId}`,
    { params: { pull_type: pullType } },
  );
}
