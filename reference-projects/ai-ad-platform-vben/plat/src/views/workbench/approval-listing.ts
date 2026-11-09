import type { ResourceApplication } from '#/domain/application';

export interface ApprovalListingFilters {
  departmentId?: string;
  requesterId?: string;
}

export type ApprovalListingRecord = ResourceApplication;

export function filterApprovalApplications(
  records: readonly ApprovalListingRecord[],
  filters: ApprovalListingFilters,
) {
  return records.filter(
    (record) =>
      (!filters.departmentId || record.departmentId === filters.departmentId) &&
      (!filters.requesterId || record.requesterId === filters.requesterId),
  );
}

export function getApprovalDepartmentLabel(record: ApprovalListingRecord) {
  return record.departmentName?.trim() || '未设置';
}
