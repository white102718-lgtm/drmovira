import { queryMaterialSettlementTaskLineSpendsApi } from '#/api/material-settlement';

/** 素材师结算月报中固化的任务线快照；任务线 ID 对应项目管理的代理线 ID。 */
export interface MaterialSettlementTaskLineSnapshot {
  /** 提交时从广告看板读取的代理线花费；无数据时为 null。 */
  spend?: null | number;
  /** 与提交时花费金额对应的币种。 */
  currency?: string;
  id: string;
  name: string;
  pitcherId: string;
  pitcherName: string;
  platform: string;
  projectId: string;
  projectName: string;
}

/** 素材师结算月报固定表单值。关联关系始终同时保存稳定 ID 和提交时名称快照。 */
export interface MaterialSettlementReportFormValue {
  commissionRatio: number;
  platforms: string[];
  pitcherIds: string[];
  pitcherNames: string[];
  projectIds: string[];
  projectNames: string[];
  remark: string;
  settlementMonth: string;
  taskLineIds: string[];
  taskLineNames: string[];
  taskLines: MaterialSettlementTaskLineSnapshot[];
}

function taskLineSpendKey(projectName: string, taskLineName: string) {
  return `${projectName.trim()}\u0000${taskLineName.trim()}`;
}

/**
 * 查询每条任务线在结算月份内的花费。
 *
 * @remarks
 * 由主业务服务按“项目 + 代理线 + 结算月份”精确筛选 Doris 明细；详情弹窗和提交快照均只发起一次请求。
 */
export async function queryMaterialSettlementTaskLineSpends(
  settlementMonth: string,
  taskLines: MaterialSettlementTaskLineSnapshot[],
): Promise<MaterialSettlementTaskLineSnapshot[]> {
  if (!/^\d{4}-\d{2}$/.test(settlementMonth)) {
    throw new Error('结算月份格式无效');
  }

  const spends = await queryMaterialSettlementTaskLineSpendsApi(
    settlementMonth,
    taskLines.map((taskLine) => ({
      projectName: taskLine.projectName,
      taskLineName: taskLine.name,
    })),
  );
  const spendsByTaskLine = new Map(
    spends.map((spend) => [
      taskLineSpendKey(spend.projectName, spend.taskLineName),
      spend,
    ]),
  );

  return taskLines.map((taskLine) => {
    const matchedSpend = spendsByTaskLine.get(
      taskLineSpendKey(taskLine.projectName, taskLine.name),
    );

    return {
      ...taskLine,
      currency: matchedSpend?.currency ?? '',
      spend: matchedSpend?.amount ?? null,
    };
  });
}

/**
 * 生成日报提交字段。审批申请保留结构化快照，日报表则使用字符串字段兼容现有通用表。
 */
export function createMaterialSettlementReportFields(
  value: MaterialSettlementReportFormValue,
  materialDesignerName: string,
) {
  const createdAt = new Date().toISOString();
  const commissionRatio = String(value.commissionRatio);

  return {
    commissionRate: commissionRatio,
    commissionRatio,
    contactPerson: value.pitcherNames.join('、'),
    createdAt: createdAt.slice(0, 10),
    materialDesignerName,
    platforms: value.platforms.join('、'),
    pitcherIds: value.pitcherIds.join(','),
    pitcherNames: value.pitcherNames.join('、'),
    projectIds: value.projectIds.join(','),
    projectNames: value.projectNames.join('、'),
    remark: value.remark,
    reviewStatus: '已提交',
    settlementMonth: value.settlementMonth,
    taskLineIds: value.taskLineIds.join(','),
    taskLineNames: value.taskLineNames.join('、'),
    taskLineSnapshot: JSON.stringify(value.taskLines),
    // 新系统尚未建立代理线到结算消耗的统一统计口径，不能伪造为 0。
    totalSpend: '',
  };
}
