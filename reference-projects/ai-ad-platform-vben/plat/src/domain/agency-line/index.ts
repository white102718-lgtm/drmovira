import { HttpAgencyLineAdapter } from './adapters/http';
import { MockAgencyLineAdapter } from './adapters/mock';
import { AgencyLineService } from './service';

export type { AgencyLineAdapter } from './adapter';
export {
  HttpAgencyLineAdapter,
  normalizeLegacyAgencyLine,
} from './adapters/http';
export {
  AGENCY_LINE_STORAGE_KEY,
  demoAgencyLines,
  MockAgencyLineAdapter,
} from './adapters/mock';
export {
  parseAgencyLineImportRows,
  prepareAgencyLineImportRows,
  resolveAgencyLineImportProjectNames,
} from './bulk-import';
export {
  getAgencyLineAdCreationIssue,
  listAgencyLinesForAdCreation,
} from './create-context';
export type {
  AgencyLineAdCreationContext,
  AgencyLineAdCreationIssue,
} from './create-context';
export { AgencyLineService } from './service';
export type * from './types';
export { AgencyLineInputError, normalizeAgencyLineInput } from './validation';

const useMockAdapter = import.meta.env.VITE_FUSION_DEMO_MODE === 'true';

export const agencyLineService = new AgencyLineService(
  useMockAdapter ? new MockAgencyLineAdapter() : new HttpAgencyLineAdapter(),
);
