import type { AgencyLine } from '#/domain/agency-line';

import { isFusionDemoMode } from '#/api/fusion/mode';
import {
  changeProjectAgencyLineStatus,
  getCompletedProjectTasks,
} from '#/api/project-operating';
import { agencyLineService } from '#/domain/agency-line';

import { projectService } from './index';

/** 详情仅展示投放、素材任务；演示模式过滤历史媒介样例。 */
export async function listCompletedProjectTasks(
  id: string,
  page = 1,
  pageSize = 10,
) {
  if (!isFusionDemoMode()) return getCompletedProjectTasks(id, page, pageSize);
  const overview = await projectService.getOperatingOverview(id);
  const tasks = overview.completedTasks.filter((task) => task.kind !== 'media');
  return {
    items: tasks.slice((page - 1) * pageSize, page * pageSize),
    page,
    pageSize,
    total: tasks.length,
  };
}

/** 每次最多100条，正式模式由后端校验归属并原子提交。 */
export async function setProjectAgencyLineStatus(
  id: string,
  ids: string[],
  status: 'active' | 'stopped',
) {
  if (
    !id ||
    !ids.length ||
    ids.length > 100 ||
    !['active', 'stopped'].includes(status)
  ) {
    throw new Error('请选择1至100条代理线和有效状态');
  }
  const uniqueIds = [...new Set(ids)];
  if (!isFusionDemoMode())
    return changeProjectAgencyLineStatus(id, uniqueIds, status);
  const project = await projectService.get(id);
  if (['ended', 'archived'].includes(project.status))
    throw new Error('结束或归档项目不可修改代理线');
  const lines = await Promise.all(
    uniqueIds.map((lineId) => agencyLineService.get(lineId)),
  );
  if (lines.some((line) => !project.agencyLineIds?.includes(line.id)))
    throw new Error('所选代理线不属于当前项目');
  for (const line of lines) await agencyLineService.save({ ...line, status });
}

/** 导出当前项目全部代理线，按分页接口读取，避免只导出当前页。 */
export async function listAllProjectAgencyLines(
  projectId: string,
): Promise<AgencyLine[]> {
  const rows: AgencyLine[] = [];
  for (let page = 1; ; page += 1) {
    const result = await agencyLineService.list({
      page,
      pageSize: 100,
      projectId,
    });
    rows.push(...result.items);
    if (rows.length >= result.total) return rows;
    if (!result.items.length)
      throw new Error('代理线数据发生变化，请刷新后重试');
  }
}

/** CSV 单元格按文本导出，避免用户填写内容被电子表格识别为公式。 */
export function agencyLinesCsv(lines: AgencyLine[]) {
  const cell = (value: string) =>
    `"${(/^[\s]*[=+\-@\t\r\n]/.test(value) ? `'${value}` : value).replaceAll('"', '""')}"`;
  const rows = [
    ['投手', '投放平台', '代理线', '像素名称', '状态'],
    ...lines.map((line) => [
      line.optimizerName || '未分配',
      line.platform,
      line.name,
      line.pixelName || '',
      line.status === 'stopped' ? '已停投' : '进行中',
    ]),
  ];
  return `\uFEFF${rows.map((row) => row.map(cell).join(',')).join('\r\n')}`;
}
