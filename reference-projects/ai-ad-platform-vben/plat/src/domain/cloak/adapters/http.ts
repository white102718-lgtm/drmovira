import type { CloakAdapter } from '../adapter';
import type {
  CloakBatchCreateInput,
  CloakBatchResult,
  CloakCountryOption,
  CloakDomainOption,
  CloakRecordPage,
  CloakRecordQuery,
  CloakRecordSheetWritebackResult,
  CloakSheetWritebackResult,
} from '../types';

import { mainBackendClient } from '#/api/request';

export class HttpCloakAdapter implements CloakAdapter {
  createBatch(input: CloakBatchCreateInput): Promise<CloakBatchResult> {
    return mainBackendClient.post('/cloak/batch', input);
  }

  deleteRecords(ids: string[]): Promise<void> {
    return mainBackendClient.delete<void>(`/cloak/records/${ids.join(',')}`);
  }

  listCountries(): Promise<CloakCountryOption[]> {
    return mainBackendClient.get('/cloak/countries');
  }

  listDomains(): Promise<CloakDomainOption[]> {
    return mainBackendClient.get('/cloak/domains');
  }

  listOccupiedAgencyLineIds(projectId: string): Promise<string[]> {
    return mainBackendClient.get(
      `/cloak/projects/${encodeURIComponent(projectId)}/occupied-agency-lines`,
    );
  }

  listRecords(query: CloakRecordQuery): Promise<CloakRecordPage> {
    return mainBackendClient.get('/cloak/records', { params: query });
  }

  writebackSheet(batchId: string): Promise<CloakSheetWritebackResult> {
    return mainBackendClient.post<CloakSheetWritebackResult>(
      `/cloak/batches/${encodeURIComponent(batchId)}/sheet-writeback`,
    );
  }

  writebackRecords(ids: string[]): Promise<CloakRecordSheetWritebackResult> {
    return mainBackendClient.post<CloakRecordSheetWritebackResult>(
      '/cloak/records/sheet-writeback',
      { recordIds: ids },
    );
  }
}
