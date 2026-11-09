import type {
  PersonnelDashboardListQuery,
  PersonnelDashboardListResult,
} from './types';

export interface PersonnelDashboardAdapter {
  list(
    query: PersonnelDashboardListQuery,
  ): Promise<PersonnelDashboardListResult>;
}
