import type { DeliverySourceCampaign, DeliverySourceQuery } from './types';

/** Compatibility boundary around the legacy delivery-center read endpoint. */
export interface DeliverySourceAdapter {
  listCampaigns(query?: DeliverySourceQuery): Promise<DeliverySourceCampaign[]>;
}
