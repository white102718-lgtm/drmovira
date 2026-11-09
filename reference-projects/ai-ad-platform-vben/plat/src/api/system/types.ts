export interface SystemPageResult<T> {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
}
