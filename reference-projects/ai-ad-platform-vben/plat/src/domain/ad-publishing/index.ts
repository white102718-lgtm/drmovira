import { HttpAdPublishingAdapter } from './adapters/http';
import { AdPublishingService } from './service';

export type * from './adapter';
export { HttpAdPublishingAdapter } from './adapters/http';
export { AdPublishingService } from './service';
export type * from './types';

/** Default service preserves the old Fusion API implementation behind an adapter. */
export const adPublishingService = new AdPublishingService(
  new HttpAdPublishingAdapter(),
);
