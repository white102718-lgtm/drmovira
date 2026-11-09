import type { DeliverySourceAdapter } from './adapter';
import type {
  DeliveryAcceptanceRecord,
  DeliveryCompletionState,
  DeliverySourceCampaign,
  DeliverySourceQuery,
  DeliverySourceSnapshot,
  DeliverySubmissionInput,
  DeliverySubmissionRecord,
} from './types';

function createSubmissionId() {
  return `SUBMISSION-${Date.now()}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`;
}

function nowText() {
  return new Date().toLocaleString('zh-CN', { hour12: false });
}

function uniqueNonEmpty(values: readonly string[] | undefined) {
  return [...new Set(values?.map((value) => value.trim()).filter(Boolean))];
}

function validateNonNegativeInteger(value: number) {
  return Number.isInteger(value) && value >= 0;
}

export class DeliverySourceService {
  constructor(private readonly adapter: DeliverySourceAdapter) {}

  /**
   * Converts one read-only campaign selection into the persisted delivery
   * submission fields. Unknown ad set/ad IDs are rejected rather than being
   * silently sent as hand-written source data.
   */
  createSnapshot(
    campaign: DeliverySourceCampaign,
    sourceAdsetIds: readonly string[],
    sourceAdIds: readonly string[] = [],
  ): DeliverySourceSnapshot {
    const selectedAdsetIds = uniqueNonEmpty(sourceAdsetIds);
    if (selectedAdsetIds.length === 0) {
      throw new Error('请至少选择 1 个广告计划组');
    }

    const adSetsById = new Map(
      campaign.adSets.map((adSet) => [adSet.id, adSet]),
    );
    const unknownAdSetId = selectedAdsetIds.find((id) => !adSetsById.has(id));
    if (unknownAdSetId) {
      throw new Error(`广告计划组不存在或已变更：${unknownAdSetId}`);
    }

    const selectedAdSets = selectedAdsetIds.flatMap((id) => {
      const adSet = adSetsById.get(id);
      return adSet ? [adSet] : [];
    });
    const selectedAdIds = uniqueNonEmpty(sourceAdIds);
    const availableAds = selectedAdSets.flatMap((adSet) => adSet.ads);
    const availableAdIds = new Set(availableAds.map((ad) => ad.id));
    const unknownAdId = selectedAdIds.find((id) => !availableAdIds.has(id));
    if (unknownAdId) {
      throw new Error(
        `广告不存在、已变更或不属于所选广告计划组：${unknownAdId}`,
      );
    }

    return {
      accountId: campaign.accountId,
      accountName: campaign.accountName,
      actualBudget: selectedAdSets.reduce(
        (total, adSet) => total + adSet.dailyBudget,
        0,
      ),
      actualStartAt: campaign.startedAt,
      adCount:
        selectedAdIds.length > 0
          ? selectedAdIds.length
          : selectedAdSets.reduce((total, adSet) => total + adSet.adCount, 0),
      adsetCount: selectedAdSets.length,
      agencyLineId: campaign.agencyLineId,
      agencyLineName: campaign.agencyLineName,
      campaignCount: 1,
      campaignIds: [campaign.id],
      campaignName: campaign.name,
      currency: campaign.currency,
      dataCutoffAt: campaign.dataCutoffAt ?? campaign.syncedAt,
      deliveryStatus: campaign.status,
      materialVersion: campaign.materialVersion,
      platform: campaign.platform,
      projectId: campaign.projectId,
      sourceAdIds: selectedAdIds,
      sourceAdsetIds: selectedAdsetIds,
      sourceSyncedAt: campaign.syncedAt,
    };
  }

  listCampaigns(
    query: DeliverySourceQuery = {},
  ): Promise<DeliverySourceCampaign[]> {
    return this.adapter.listCampaigns(query);
  }
}

export class DeliveryWorkflowService {
  accept(
    state: DeliveryCompletionState,
    reviewer: string,
    reason = '',
    reviewerId?: string,
  ): {
    acceptance: DeliveryAcceptanceRecord;
    completion: DeliveryCompletionState;
  } {
    const current = state.current;
    if (!current || current.status !== 'submitted' || !reviewer.trim()) {
      throw new Error('当前交付不可验收');
    }
    const acceptance: DeliveryAcceptanceRecord = {
      decision: 'accepted',
      reason: reason.trim(),
      reviewedAt: nowText(),
      reviewerId: reviewerId?.trim() || undefined,
      reviewer: reviewer.trim(),
      submissionId: current.submissionId,
      versionNo: current.versionNo,
    };
    return {
      acceptance,
      completion: {
        acceptanceHistory: [...state.acceptanceHistory, acceptance],
        current: { ...current, status: 'accepted' },
        history: [...state.history],
      },
    };
  }

  isSubmissionValid(input: DeliverySubmissionInput) {
    const entryMode = input.entryMode ?? 'manual';
    const campaignIds = uniqueNonEmpty(input.campaignIds);
    const adsetIds = uniqueNonEmpty(input.sourceAdsetIds);
    const adIds = uniqueNonEmpty(input.sourceAdIds);

    return Boolean(
      input.submittedBy.trim() &&
        input.platform.trim() &&
        input.accountId.trim() &&
        input.actualStartAt &&
        campaignIds.length > 0 &&
        validateNonNegativeInteger(input.campaignCount) &&
        input.campaignCount >= campaignIds.length &&
        validateNonNegativeInteger(input.adsetCount) &&
        input.adsetCount >= adsetIds.length &&
        validateNonNegativeInteger(input.adCount) &&
        input.adCount >= adIds.length &&
        Number.isFinite(input.actualBudget) &&
        input.actualBudget > 0 &&
        input.currency.trim() &&
        (entryMode === 'delivery-center'
          ? Boolean(input.sourceSyncedAt && input.dataCutoffAt)
          : input.files.length > 0) &&
        (input.deliveryStatus !== 'partial' || input.exceptionNote.trim()),
    );
  }

  reject(
    state: DeliveryCompletionState,
    reviewer: string,
    reason: string,
    reviewerId?: string,
  ): {
    acceptance: DeliveryAcceptanceRecord;
    completion: DeliveryCompletionState;
  } {
    const current = state.current;
    if (
      !current ||
      current.status !== 'submitted' ||
      !reviewer.trim() ||
      !reason.trim()
    ) {
      throw new Error('打回交付时必须填写原因');
    }
    const acceptance: DeliveryAcceptanceRecord = {
      decision: 'rejected',
      reason: reason.trim(),
      reviewedAt: nowText(),
      reviewerId: reviewerId?.trim() || undefined,
      reviewer: reviewer.trim(),
      submissionId: current.submissionId,
      versionNo: current.versionNo,
    };
    return {
      acceptance,
      completion: {
        acceptanceHistory: [...state.acceptanceHistory, acceptance],
        current: { ...current, status: 'rejected' },
        history: [...state.history],
      },
    };
  }

  submit(
    state: DeliveryCompletionState,
    input: DeliverySubmissionInput,
  ): DeliveryCompletionState {
    if (!this.isSubmissionValid(input)) {
      throw new Error('投放交付信息不完整或不符合校验规则');
    }

    const history: DeliverySubmissionRecord[] = state.current
      ? [
          ...state.history,
          {
            ...state.current,
            status:
              state.current.status === 'rejected' ? 'rejected' : 'superseded',
          },
        ]
      : [...state.history];
    const versionNo =
      Math.max(0, ...history.map((record) => record.versionNo)) + 1;
    const record: DeliverySubmissionRecord = {
      ...input,
      campaignIds: uniqueNonEmpty(input.campaignIds),
      sourceAdIds: uniqueNonEmpty(input.sourceAdIds),
      sourceAdsetIds: uniqueNonEmpty(input.sourceAdsetIds),
      status: 'submitted',
      submissionId: createSubmissionId(),
      submittedAt: nowText(),
      versionNo,
    };

    return {
      acceptanceHistory: [...state.acceptanceHistory],
      current: record,
      history,
    };
  }
}
