import type { CloakAdapter } from './adapter';
import type {
  CloakBatchCreateInput,
  CloakBatchResult,
  CloakCountryOption,
  CloakDomainOption,
  CloakRecordPage,
  CloakRecordQuery,
  CloakRecordSheetWritebackResult,
  CloakSheetWritebackResult,
} from './types';

/** 斗篷配置领域服务。 */
export class CloakService {
  constructor(private readonly adapter: CloakAdapter) {}

  createBatch(input: CloakBatchCreateInput): Promise<CloakBatchResult> {
    return this.adapter.createBatch(input);
  }

  deleteRecords(ids: string[]): Promise<void> {
    return this.adapter.deleteRecords(ids);
  }

  listCountries(): Promise<CloakCountryOption[]> {
    return this.adapter.listCountries();
  }

  listDomains(): Promise<CloakDomainOption[]> {
    return this.adapter.listDomains();
  }

  listOccupiedAgencyLineIds(projectId: string): Promise<string[]> {
    return this.adapter.listOccupiedAgencyLineIds(projectId);
  }

  listRecords(query: CloakRecordQuery): Promise<CloakRecordPage> {
    return this.adapter.listRecords(query);
  }

  writebackSheet(batchId: string): Promise<CloakSheetWritebackResult> {
    return this.adapter.writebackSheet(batchId);
  }

  writebackRecords(ids: string[]): Promise<CloakRecordSheetWritebackResult> {
    return this.adapter.writebackRecords(ids);
  }
}
