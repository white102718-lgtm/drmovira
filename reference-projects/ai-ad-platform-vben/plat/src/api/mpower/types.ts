export interface MpowerBody<T> {
  code: number | string;
  data: T;
  msg?: string;
}

export interface MpowerPage<T> {
  current?: number;
  pages?: number;
  records: T[];
  size?: number;
  total: number;
}

export interface MpowerTable<T> {
  code: number | string;
  msg?: string;
  rows: T[];
  total: number;
}

export interface MpowerPageQuery {
  pageNum?: number;
  pageSize?: number;
  [key: string]: unknown;
}

export type MpowerRecord = Record<string, unknown>;
