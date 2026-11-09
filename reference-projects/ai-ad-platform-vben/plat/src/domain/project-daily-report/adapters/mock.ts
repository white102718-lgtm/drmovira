import type { ProjectDailyReportAdapter } from '../adapter';
import type {
  ProjectDailyReportImportResult,
  ProjectDailyReportOption,
  ProjectDailyReportQuery,
  ProjectDailyReportResult,
  ProjectDailyReportSyncStatus,
} from '../types';

import {
  PROJECT_DAILY_REPORT_MOCK_UPDATED_AT,
  projectDailyReportMockRows,
} from '../mock-data';

function uniqueOptions(
  rows: typeof projectDailyReportMockRows,
  pick: 'agencyLine' | 'agencyLineItem' | 'project',
): ProjectDailyReportOption[] {
  const seen = new Map<string, ProjectDailyReportOption>();
  for (const row of rows) {
    if (pick === 'project') {
      seen.set(row.projectId, { id: row.projectId, name: row.projectName });
      continue;
    }
    if (pick === 'agencyLine') {
      seen.set(row.agencyLineId, {
        id: row.agencyLineId,
        name: row.agencyLineName,
        projectId: row.projectId,
      });
      continue;
    }
    seen.set(row.agencyLineItemId, {
      agencyLineId: row.agencyLineId,
      id: row.agencyLineItemId,
      name: row.agencyLineItemName,
      projectId: row.projectId,
    });
  }
  return [...seen.values()];
}

const idleSync = (): ProjectDailyReportSyncStatus => ({
  alreadyRunning: false,
  errorMessage: null,
  finishedAt: PROJECT_DAILY_REPORT_MOCK_UPDATED_AT,
  id: 'mock-sync',
  rowCount: projectDailyReportMockRows.length,
  startedAt: PROJECT_DAILY_REPORT_MOCK_UPDATED_AT,
  status: 'succeeded',
  triggerType: 'schedule',
});

export class MockProjectDailyReportAdapter
  implements ProjectDailyReportAdapter
{
  async getSyncStatus(): Promise<ProjectDailyReportSyncStatus> {
    return idleSync();
  }

  async query(
    _input: ProjectDailyReportQuery,
  ): Promise<ProjectDailyReportResult> {
    return {
      agencyLineItems: uniqueOptions(
        projectDailyReportMockRows,
        'agencyLineItem',
      ),
      agencyLines: uniqueOptions(projectDailyReportMockRows, 'agencyLine'),
      projects: uniqueOptions(projectDailyReportMockRows, 'project'),
      rows: projectDailyReportMockRows.map((row) => ({
        ...row,
        retention: { ...row.retention },
      })),
      summary: {
        averageRetention7: null,
        currency: 'BRL',
        firstDepositAmount: 0,
        firstDepositUsers: 0,
        rechargeAmount: 0,
        spendAmount: 0,
        withdrawalAmount: 0,
      },
      updatedAt: PROJECT_DAILY_REPORT_MOCK_UPDATED_AT,
    };
  }

  async startSync(): Promise<ProjectDailyReportSyncStatus> {
    return idleSync();
  }

  async importExcel(_file: File): Promise<ProjectDailyReportImportResult> {
    return {
      files: 1,
      projects: uniqueOptions(projectDailyReportMockRows, 'project'),
      rowCount: projectDailyReportMockRows.length,
      skippedFiles: [],
      skippedRows: 0,
      updatedAt: PROJECT_DAILY_REPORT_MOCK_UPDATED_AT,
    };
  }
}
