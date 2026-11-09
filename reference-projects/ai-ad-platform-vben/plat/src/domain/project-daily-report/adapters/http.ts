import type { ProjectDailyReportAdapter } from '../adapter';
import type {
  ProjectDailyReportImportResult,
  ProjectDailyReportQuery,
  ProjectDailyReportResult,
  ProjectDailyReportSyncStatus,
} from '../types';

import {
  getProjectDailyReportApi,
  getProjectDailyReportSyncApi,
  importProjectDailyReportApi,
  startProjectDailyReportSyncApi,
} from '#/api/project-daily-report';

export class HttpProjectDailyReportAdapter
  implements ProjectDailyReportAdapter
{
  getSyncStatus(): Promise<ProjectDailyReportSyncStatus> {
    return getProjectDailyReportSyncApi();
  }

  importExcel(file: File): Promise<ProjectDailyReportImportResult> {
    return importProjectDailyReportApi(file);
  }

  query(input: ProjectDailyReportQuery): Promise<ProjectDailyReportResult> {
    return getProjectDailyReportApi(input);
  }

  startSync(): Promise<ProjectDailyReportSyncStatus> {
    return startProjectDailyReportSyncApi();
  }
}