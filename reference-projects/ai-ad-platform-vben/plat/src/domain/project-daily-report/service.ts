import type {
  ProjectDailyReportAdapter,
  ProjectDailyReportImportResult,
  ProjectDailyReportQuery,
  ProjectDailyReportResult,
  ProjectDailyReportRow,
  ProjectDailyReportSummary,
  ProjectDailyReportSyncStatus,
} from './types';

function inRange(date: string, startDate: string, endDate: string) {
  return date >= startDate && date <= endDate;
}

function average(values: number[]) {
  if (values.length === 0) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function summarize(
  rows: ProjectDailyReportRow[],
  fallbackCurrency: string,
): ProjectDailyReportSummary {
  const retention7 = rows
    .map((row) => row.retention[7])
    .filter((value): value is number => typeof value === 'number');

  return {
    averageRetention7: average(retention7),
    currency: rows[0]?.currency || fallbackCurrency,
    firstDepositAmount: rows.reduce(
      (sum, row) => sum + row.firstDepositAmount,
      0,
    ),
    firstDepositUsers: rows.reduce(
      (sum, row) => sum + row.firstDepositUsers,
      0,
    ),
    rechargeAmount: rows.reduce((sum, row) => sum + row.rechargeAmount, 0),
    spendAmount: rows.reduce((sum, row) => sum + row.spendAmount, 0),
    withdrawalAmount: rows.reduce((sum, row) => sum + row.withdrawalAmount, 0),
  };
}

/**
 * 过滤与汇总项目日报。金额与人数只做筛选范围内的加总，7 日留存取有值行的均值。
 */
export class ProjectDailyReportService {
  constructor(private readonly adapter: ProjectDailyReportAdapter) {}

  async query(
    input: ProjectDailyReportQuery,
  ): Promise<ProjectDailyReportResult> {
    const source = await this.adapter.query(input);
    // HTTP 已按筛选分页并算好汇总；再滤一次会把当页当成全集。
    if (typeof source.total === 'number') {
      return source;
    }
    const rows = source.rows
      .filter((row) => {
        if (input.projectId && row.projectId !== input.projectId) return false;
        if (input.agencyLineId && row.agencyLineId !== input.agencyLineId) {
          return false;
        }
        if (
          input.agencyLineItemId &&
          row.agencyLineItemId !== input.agencyLineItemId
        ) {
          return false;
        }
        return inRange(row.date, input.startDate, input.endDate);
      })
      .sort((left, right) => {
        if (left.date !== right.date)
          return right.date.localeCompare(left.date);
        return left.agencyLineItemName.localeCompare(
          right.agencyLineItemName,
          'zh-CN',
        );
      });

    return {
      agencyLineItems: source.agencyLineItems ?? [],
      agencyLines: source.agencyLines ?? [],
      projects: source.projects ?? [],
      rows,
      summary: summarize(rows, source.summary.currency),
      total: rows.length,
      updatedAt: source.updatedAt,
    };
  }

  getSyncStatus(): Promise<ProjectDailyReportSyncStatus> {
    return this.adapter.getSyncStatus();
  }

  startSync(): Promise<ProjectDailyReportSyncStatus> {
    return this.adapter.startSync();
  }

  importExcel(file: File): Promise<ProjectDailyReportImportResult> {
    return this.adapter.importExcel(file);
  }
}
