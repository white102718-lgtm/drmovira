import { isFusionDemoMode } from '#/api/fusion/mode';

import { HttpProjectDailyReportAdapter } from './adapters/http';
import { MockProjectDailyReportAdapter } from './adapters/mock';
import { ProjectDailyReportService } from './service';

export type { ProjectDailyReportAdapter } from './adapter';
export { HttpProjectDailyReportAdapter } from './adapters/http';
export { MockProjectDailyReportAdapter } from './adapters/mock';
export { PROJECT_DAILY_RETENTION_DAYS } from './types';
export { ProjectDailyReportService } from './service';
export type * from './types';

/**
 * 演示环境使用本地样例；正式环境读取 Doris 中已落库的项目日报。
 */
export const projectDailyReportService = new ProjectDailyReportService(
  isFusionDemoMode()
    ? new MockProjectDailyReportAdapter()
    : new HttpProjectDailyReportAdapter(),
);
