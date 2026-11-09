import type { DeliverySourceAdapter } from '../adapter';
import type { DeliverySourceCampaign, DeliverySourceQuery } from '../types';

import { getDeliveryCenterCampaignOptionsApi } from '#/api/fusion/delivery-options';

/**
 * Keeps `/fusion/delivery/campaign-options` intact while giving the task
 * domain one read-model entry point. The formal API can replace this adapter
 * without changing task-center routes or persisted task records.
 */
export class LegacyDeliverySourceAdapter implements DeliverySourceAdapter {
  async listCampaigns(
    query: DeliverySourceQuery = {},
  ): Promise<DeliverySourceCampaign[]> {
    const campaigns = await getDeliveryCenterCampaignOptionsApi(query);
    return campaigns.map((campaign) => ({
      ...campaign,
      // Old endpoint payloads did not have the optional Ad or data-cutoff
      // fields. Normalize them here instead of making existing integrations
      // fail while the formal source API is rolling out.
      adSets: campaign.adSets.map((adSet) => ({
        ...adSet,
        ads: Array.isArray(adSet.ads) ? adSet.ads.map((ad) => ({ ...ad })) : [],
      })),
      dataCutoffAt: campaign.dataCutoffAt ?? campaign.syncedAt,
    }));
  }
}
