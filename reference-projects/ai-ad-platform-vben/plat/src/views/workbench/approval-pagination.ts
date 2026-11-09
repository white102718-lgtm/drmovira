export function paginateApprovalRecords<T>(
  records: readonly T[],
  page: number,
  pageSize: number,
) {
  const start = (page - 1) * pageSize;
  return records.slice(start, start + pageSize);
}

export function limitApprovalBatchRecords<T>(
  records: readonly T[],
  limit: number,
) {
  return records.slice(0, limit);
}

export function resolveApprovalPageChange(
  currentPageSize: number,
  requestedPage: number,
  requestedPageSize: number,
) {
  return {
    page: requestedPageSize === currentPageSize ? requestedPage : 1,
    pageSize: requestedPageSize,
  };
}

export function isLatestApprovalRequest(
  requestSequence: number,
  currentSequence: number,
) {
  return requestSequence === currentSequence;
}
