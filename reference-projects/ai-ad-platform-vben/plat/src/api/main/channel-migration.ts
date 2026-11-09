import { mainBackendClient } from '#/api/request';

/** 渠道增量迁移预检条目，来源 ID 始终按字符串处理。 */
export interface ChannelMigrationCandidate {
  action: 'CONFLICT' | 'INSERT';
  channelCode?: string;
  channelName: string;
  conflict?: string;
  rateCount: number;
  sourceId: string;
}

/** 当前部署环境实时生成的渠道增量迁移计划。 */
export interface ChannelMigrationPlan {
  environment: 'PRODUCTION' | 'TEST';
  items: ChannelMigrationCandidate[];
  mappedCount: number;
  missingCount: number;
  planHash: string;
  sourceCount: number;
}

export interface ChannelMigrationResult {
  batchKey: string;
  channelCount: number;
  environment: 'PRODUCTION' | 'TEST';
  rateCount: number;
}

/** 扫描全部缺口，或只预检指定的老渠道 ID。 */
export function createChannelMigrationPlan(sourceIds: string[] = []) {
  return mainBackendClient.post<ChannelMigrationPlan>(
    '/internal/migrations/channels/plans',
    { sourceIds },
    { timeout: 180_000 },
  );
}

/** 执行时服务端会重新计算计划哈希，来源或目标变化会拒绝写入。 */
export function executeChannelMigration(sourceIds: string[], planHash: string) {
  return mainBackendClient.post<ChannelMigrationResult>(
    '/internal/migrations/channels/execute',
    { confirmed: true, planHash, sourceIds },
    { timeout: 180_000 },
  );
}

export interface MigrationEnvironment {
  targetEnvironment: 'PRODUCTION' | 'TEST';
  targetSchema: string;
}

export interface AssetMigrationJob {
  id: string;
  state: string;
  planHash: null | string;
  sourceCount: number;
  total: number;
  completed: number;
  isolated: number;
  duplicates: number;
  error: null | string;
}

export interface AssetMigrationItem {
  id: string;
  accountId: string;
  targetId: null | string;
  action: string;
  state: string;
  reason: null | string;
  beforeJson: null | string;
  desiredJson: null | string;
  afterJson: null | string;
}

const assetPath = '/internal/migrations/channel-account-assets';

export function getMigrationEnvironment() {
  return mainBackendClient.get<MigrationEnvironment>(
    `${assetPath}/environment`,
  );
}

export function listAssetMigrationJobs() {
  return mainBackendClient.get<AssetMigrationJob[]>(`${assetPath}/jobs`);
}

export function createAssetMigrationPlan() {
  return mainBackendClient.post<AssetMigrationJob>(`${assetPath}/plans`);
}

export function getAssetMigrationJob(id: string) {
  return mainBackendClient.get<AssetMigrationJob>(
    `${assetPath}/${encodeURIComponent(id)}`,
  );
}

export function getAssetMigrationItems(
  id: string,
  afterId = '0',
  state?: string,
) {
  return mainBackendClient.get<{
    items: AssetMigrationItem[];
    nextAfterId: null | string;
  }>(`${assetPath}/${encodeURIComponent(id)}/items`, {
    params: { afterId, state },
  });
}

export function executeAssetMigration(id: string, planHash: string) {
  return mainBackendClient.post<AssetMigrationJob>(
    `${assetPath}/${encodeURIComponent(id)}/execute`,
    {
      acceptAutomaticSync: true,
      acceptAvailableInventory: true,
      planHash,
    },
  );
}
