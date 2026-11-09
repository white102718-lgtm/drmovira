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

/** 斗篷配置数据源。 */
export interface CloakAdapter {
  createBatch(input: CloakBatchCreateInput): Promise<CloakBatchResult>;
  deleteRecords(ids: string[]): Promise<void>;
  listCountries(): Promise<CloakCountryOption[]>;
  listDomains(): Promise<CloakDomainOption[]>;
  listOccupiedAgencyLineIds(projectId: string): Promise<string[]>;
  listRecords(query: CloakRecordQuery): Promise<CloakRecordPage>;
  writebackSheet(batchId: string): Promise<CloakSheetWritebackResult>;
  writebackRecords(ids: string[]): Promise<CloakRecordSheetWritebackResult>;
}
