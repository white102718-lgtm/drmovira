export type DeliveryEntryMode = 'delivery-center' | 'manual';

export type DeliveryRecordStatus = 'active' | 'failed' | 'partial' | 'paused';

export interface DeliveryProofFile {
  hash?: string;
  id: string;
  name: string;
  objectKey?: string;
  size: number;
  source?: string;
  type: string;
  uploadedAt?: string;
  url?: string;
}

export interface DeliverySourceAd {
  id: string;
  name: string;
  status: DeliveryRecordStatus;
}

export interface DeliverySourceAdSet {
  adCount: number;
  ads: DeliverySourceAd[];
  dailyBudget: number;
  id: string;
  name: string;
  status: DeliveryRecordStatus;
}

/**
 * Read-only record returned by the delivery-center compatibility endpoint.
 * The old API remains the source adapter until the formal delivery API lands.
 */
export interface DeliverySourceCampaign {
  accountId: string;
  accountName: string;
  adSets: DeliverySourceAdSet[];
  agencyLineId?: string;
  agencyLineName?: string;
  currency: string;
  dailyBudget: number;
  dataCutoffAt?: string;
  id: string;
  materialVersion?: string;
  name: string;
  platform: string;
  projectId: string;
  projectName: string;
  startedAt: string;
  status: DeliveryRecordStatus;
  syncedAt: string;
}

export interface DeliverySourceQuery {
  forceSync?: boolean;
  projectId?: string;
  projectName?: string;
}

export interface DeliverySourceSnapshot {
  accountId: string;
  accountName: string;
  actualBudget: number;
  actualStartAt: string;
  adCount: number;
  adsetCount: number;
  agencyLineId?: string;
  agencyLineName?: string;
  campaignCount: number;
  campaignIds: string[];
  campaignName: string;
  currency: string;
  dataCutoffAt: string;
  deliveryStatus: DeliveryRecordStatus;
  materialVersion?: string;
  platform: string;
  projectId: string;
  sourceAdIds: string[];
  sourceAdsetIds: string[];
  sourceSyncedAt: string;
}

export interface DeliverySubmissionInput {
  accountId: string;
  accountName?: string;
  actualBudget: number;
  actualSpend?: number;
  actualStartAt: string;
  adCount: number;
  adsetCount: number;
  agencyLineId?: string;
  agencyLineName?: string;
  campaignCount: number;
  campaignIds: string[];
  currency: string;
  dailyReportSpend?: number;
  dataCutoffAt?: string;
  deliveryStatus: DeliveryRecordStatus;
  entryMode?: DeliveryEntryMode;
  exceptionNote: string;
  files: DeliveryProofFile[];
  materialVersion?: string;
  note: string;
  platform: string;
  sourceAdIds?: string[];
  sourceAdsetIds?: string[];
  sourceCampaignName?: string;
  sourceSyncedAt?: string;
  submittedBy: string;
}

export type DeliverySubmissionRecordStatus =
  | 'accepted'
  | 'rejected'
  | 'submitted'
  | 'superseded';

export interface DeliverySubmissionRecord extends DeliverySubmissionInput {
  status: DeliverySubmissionRecordStatus;
  submissionId: string;
  submittedAt: string;
  versionNo: number;
}

export interface DeliveryAcceptanceRecord {
  decision: 'accepted' | 'rejected';
  reason: string;
  reviewedAt: string;
  reviewer: string;
  /** Additive stable reviewer relation; legacy entries only have reviewer. */
  reviewerId?: string;
  submissionId: string;
  versionNo: number;
}

export interface DeliveryCompletionState {
  acceptanceHistory: DeliveryAcceptanceRecord[];
  current?: DeliverySubmissionRecord;
  history: DeliverySubmissionRecord[];
}
