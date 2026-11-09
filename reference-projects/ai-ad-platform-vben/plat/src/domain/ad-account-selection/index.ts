import { HttpAdAccountSelectionAdapter } from './adapters/http';
import { MockAdAccountSelectionAdapter } from './adapters/mock';
import { AdAccountSelectionService } from './service';

export type { AdAccountSelectionAdapter } from './adapter';
export {
  HttpAdAccountSelectionAdapter,
  SELECTABLE_AD_ACCOUNT_ENDPOINT,
} from './adapters/http';
export {
  LEGACY_AGENCY_LINE_ID_ALIASES,
  LEGACY_MEDIA_ACCOUNT_STORAGE_KEY,
  LEGACY_MEDIA_ASSIGNMENT_STORAGE_KEY,
  LEGACY_PROJECT_ID_ALIASES,
  LEGACY_USER_ID_ALIASES,
  MockAdAccountSelectionAdapter,
} from './adapters/mock';
export {
  LEGACY_AGENCY_LINE,
  LEGACY_PROJECT_ID_BY_NAME,
  resolveLegacyAdAccountQuery,
  toLegacyAdvertiserAccount,
} from './legacy';
export { AdAccountSelectionService } from './service';
export type * from './types';

const useMockAdapter = import.meta.env.VITE_FUSION_DEMO_MODE === 'true';

export const adAccountSelectionService = new AdAccountSelectionService(
  useMockAdapter
    ? new MockAdAccountSelectionAdapter()
    : new HttpAdAccountSelectionAdapter(),
);
