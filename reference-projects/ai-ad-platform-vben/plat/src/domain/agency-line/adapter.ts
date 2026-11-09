import type {
  AgencyLine,
  AgencyLineCreateCommand,
  AgencyLineDeliveryUrlHistory,
  AgencyLineListQuery,
  AgencyLineListResult,
  AgencyLineOption,
  AgencyLineUpsertInput,
} from './types';

export interface AgencyLineAdapter {
  create(command: AgencyLineCreateCommand): Promise<AgencyLine>;
  get(id: string): Promise<AgencyLine>;
  getDeliveryUrlHistory(id: string): Promise<AgencyLineDeliveryUrlHistory[]>;
  list(query?: AgencyLineListQuery): Promise<AgencyLineListResult>;
  listOptions(query?: AgencyLineListQuery): Promise<AgencyLineOption[]>;
  remove(id: string): Promise<void>;
  save(input: AgencyLineUpsertInput): Promise<AgencyLine>;
}
