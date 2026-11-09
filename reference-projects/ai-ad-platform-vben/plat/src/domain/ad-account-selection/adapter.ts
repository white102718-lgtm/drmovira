import type { AdAccountSelectionQuery, SelectableAdAccount } from './types';

/**
 * Adapters normalize inventory candidates only. Eligibility, searching and
 * pagination deliberately remain in the domain service.
 */
export interface AdAccountSelectionAdapter {
  listCandidates(
    query?: AdAccountSelectionQuery,
  ): Promise<SelectableAdAccount[]>;
}
